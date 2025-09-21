"""
Hyperliquid utility functions and connector facades (Scaffold).
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from loguru import logger


class HyperliquidClient:
    """
    Placeholder for a thin client wrapper. Implement REST/WebSocket bindings here.
    Currently safe and read-only. No authenticated requests are performed.
    """

    def __init__(
        self,
        api_key: Optional[str] | None = None,
        api_secret: Optional[str] | None = None,
        *,
        base_url: Optional[str] | None = None,
        testnet: bool = False,
    ) -> None:
        # In a future implementation, these enable authenticated requests
        self.api_key = api_key or os.getenv("HYPERLIQUID_API_KEY")
        self.api_secret = api_secret or os.getenv("HYPERLIQUID_API_SECRET")
        # Choose endpoints (placeholders)
        env_base = os.getenv("HYPERLIQUID_BASE_URL")
        # Precedence: explicit base_url arg > testnet flag default > env override > mainnet default
        if base_url:
            self.base_url = base_url
        elif testnet:
            self.base_url = "https://api-testnet.hyperliquid.xyz"
        elif env_base:
            self.base_url = env_base
        else:
            self.base_url = "https://api.hyperliquid.xyz"
        self._client = httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(5.0, connect=5.0))
        self._universe: list[dict[str, Any]] | None = None
        self._universe_ttl_s: float = 300.0
        self._universe_expiry_ts: float = 0.0
        # Rolling latency samples per info type
        self._lat_samples: Dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))

    # --- Read-only helper methods (safe stubs) ---
    def get_orderbook(self, pair: str) -> Dict[str, Any]:
        """
        Retrieve L2 book snapshot using official Info endpoint:
        POST {base}/info with body {"type":"l2Book","coin": <coin>}
        Returns levels: [bids, asks], each a list of {px, sz, n}.
        Normalize to {bids:[[px,sz],...], asks:[[px,sz],...]}
        """
        coin = self._resolve_coin(pair)
        try:
            resp = self._post_info({"type": "l2Book", "coin": coin, "nSigFigs": None})
            if isinstance(resp, dict) and "levels" in resp:
                levels = resp.get("levels") or [[], []]
                bids_raw = levels[0] if isinstance(levels, list) and levels else []
                asks_raw = levels[1] if isinstance(levels, list) and len(levels) > 1 else []
                bids = [[float(x.get("px", 0.0)), float(x.get("sz", 0.0))] for x in bids_raw]
                asks = [[float(x.get("px", 0.0)), float(x.get("sz", 0.0))] for x in asks_raw]
                return {"pair": pair, "bids": bids, "asks": asks}
        except Exception as e:
            logger.debug("Orderbook fetch failed for {}: {}", pair, e)
        return {"pair": pair, "bids": [], "asks": []}

    def get_funding_rate(self, pair: str) -> float:
        """
        Retrieve current funding rate using official Info endpoint:
        POST {base}/info with body {"type":"metaAndAssetCtxs"}
        Response shape: [ {"universe":[{"name":"BTC"}, ...]}, [ {"funding":"0.0000125", ...}, ...] ]
        We map coin name to its corresponding funding in ctxs.
        """
        coin = _to_coin(pair)
        try:
            resp = self._post_info({"type": "metaAndAssetCtxs"})
            if isinstance(resp, list) and len(resp) >= 2:
                meta, ctxs = resp[0], resp[1]
                uni = (meta or {}).get("universe", []) if isinstance(meta, dict) else []
                if isinstance(uni, list) and isinstance(ctxs, list) and len(uni) == len(ctxs):
                    name_to_idx = {str(entry.get("name")): i for i, entry in enumerate(uni) if isinstance(entry, dict)}
                    idx = name_to_idx.get(coin)
                    if idx is not None and 0 <= idx < len(ctxs):
                        funding_str = (ctxs[idx] or {}).get("funding")
                        if funding_str is not None:
                            return float(funding_str)
        except Exception as e:
            logger.debug("Funding fetch failed for {}: {}", pair, e)
        return 0.0

    # --- Write methods (NO-OP in scaffold for safety) ---
    def place_order(self, pair: str, side: str, price: float, size: float) -> Dict[str, Any]:
        logger.debug(
            "[DRY-RUN] place_order pair={}, side={}, price={}, size={}",
            pair,
            side,
            price,
            size,
        )
        return {"status": "dry_run", "pair": pair, "side": side, "price": price, "size": size}

    def cancel_all(self, pair: str) -> Dict[str, Any]:
        logger.debug("[DRY-RUN] cancel_all pair={}", pair)
        return {"status": "dry_run", "pair": pair}

    # --- Internal helpers ---
    def _post_info(self, body: Dict[str, Any]) -> Any | None:
        retries = 3
        backoff = 0.5
        for attempt in range(retries):
            try:
                t0 = time.time()
                r = self._client.post("/info", json=body, headers={"Content-Type": "application/json"})
                elapsed_ms = (time.time() - t0) * 1000.0
                info_type = str(body.get("type"))
                if r.status_code == 200:
                    logger.debug("/info type={} attempt={} latency_ms={:.1f}", info_type, attempt + 1, elapsed_ms)
                    # Record latency
                    try:
                        self._lat_samples[info_type].append(float(elapsed_ms))
                    except Exception:
                        pass
                    return r.json()
                logger.debug(
                    "HTTP POST /info non-200: {} body={} latency_ms={:.1f}",
                    r.status_code,
                    info_type,
                    elapsed_ms,
                )
            except Exception as e:
                logger.debug("HTTP POST /info failed (attempt {}): {} type={}", attempt + 1, e, body.get("type"))
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2
        return None

    def latency_summary(self) -> Dict[str, Dict[str, float]]:
        """
        Return rolling latency stats per info type: count, mean, p50, p90 (ms).
        """
        summary: Dict[str, Dict[str, float]] = {}
        for k, dq in self._lat_samples.items():
            if not dq:
                continue
            vals = sorted(dq)
            n = len(vals)
            mean_ms = sum(vals) / n
            def perc(p: float) -> float:
                if n == 0:
                    return 0.0
                idx = max(0, min(n - 1, int(round(p * (n - 1)))))
                return vals[idx]
            summary[k] = {
                "count": float(n),
                "mean_ms": float(mean_ms),
                "p50_ms": float(perc(0.5)),
                "p90_ms": float(perc(0.9)),
            }
        return summary

    def _ensure_universe(self) -> list[dict[str, Any]]:
        now = time.time()
        if self._universe is None or now >= self._universe_expiry_ts:
            resp = self._post_info({"type": "metaAndAssetCtxs"})
            if isinstance(resp, list) and len(resp) >= 1 and isinstance(resp[0], dict):
                uni = resp[0].get("universe")
                if isinstance(uni, list):
                    self._universe = uni
                    self._universe_expiry_ts = now + self._universe_ttl_s
        return self._universe or []

    def _resolve_coin(self, pair: str) -> str:
        """
        Map a pair like BTC-USDC to the exchange coin naming used by the Info endpoint.
        Docs note BTC/USDC on app maps to UBTC/USDC on mainnet. We resolve by
        looking up the universe names and preferring an exact match; otherwise, try
        prefixed variants like 'U' + coin.
        """
        raw = _to_coin(pair)
        uni = self._ensure_universe()
        names = [str(e.get("name")) for e in uni if isinstance(e, dict) and e.get("name")]
        if raw in names:
            return raw
        # Try prefixed variants commonly used for unified assets
        candidates = [f"U{raw}", f"W{raw}"]
        for c in candidates:
            if c in names:
                return c
        return raw

    # Public helper to expose resolved coin mapping
    def resolve_coin(self, pair: str) -> str:
        return self._resolve_coin(pair)


def _to_coin(pair: str) -> str:
    """
    Convert pair like "BTC-USDC" to coin "BTC" expected by the Info endpoint.
    """
    if "-" in pair:
        return pair.split("-", 1)[0]
    return pair
