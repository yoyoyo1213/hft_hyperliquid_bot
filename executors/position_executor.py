"""
Position executor coordinates order placement/cancellation (Scaffold).
"""
from __future__ import annotations

from typing import Dict, List

from loguru import logger


class PositionExecutor:
    def __init__(
        self,
        *,
        connector_name: str,
        leverage: int,
        position_mode: str,
        dry_run: bool = True,
        testnet: bool = False,
    ) -> None:
        self.connector_name = connector_name
        self.leverage = leverage
        self.position_mode = position_mode
        self._running = False
        self._last_desired: List[Dict] = []
        self._dry_run = dry_run
        self._testnet = testnet
        # Extra safety for any non-dry-run (testnet) flow
        self._notional_cap = 5.0  # USD cap per order intent in probe mode

    def start(self) -> None:
        logger.info(
            "PositionExecutor started | connector={}, leverage={}, mode={}, dry_run={}, testnet={}",
            self.connector_name,
            self.leverage,
            self.position_mode,
            self._dry_run,
            self._testnet,
        )
        self._running = True

    def stop(self) -> None:
        logger.info("PositionExecutor stopped")
        self._running = False

    def sync_orders(self, desired_orders: List[Dict]) -> None:
        """
        Accept desired order intents and (eventually) diff vs live orders.
        Dry-run diff against last desired intents and log actions.
        Future: integrate with connector API and real open order state.
        """
        if not self._running:
            return
        curr = _normalize(desired_orders)
        prev = _normalize(self._last_desired)

        to_add = [o for o in curr if o not in prev]
        to_remove = [o for o in prev if o not in curr]

        logger.debug(
            "[DRY-RUN] Diff orders | desired={}, add={}, remove={}",
            len(curr),
            len(to_add),
            len(to_remove),
        )
        if to_add:
            logger.debug("[DRY-RUN] Adds: {}", to_add[:5] + (["..."] if len(to_add) > 5 else []))
        if to_remove:
            logger.debug("[DRY-RUN] Removes: {}", to_remove[:5] + (["..."] if len(to_remove) > 5 else []))

        # Guarded testnet execution path: only log simulated placements with caps
        if not self._dry_run and self._testnet:
            preview = []
            for o in to_add[:5]:
                capped = dict(o)
                capped["size_quote"] = float(min(capped.get("size_quote", 0.0), self._notional_cap))
                preview.append(capped)
            logger.info("[TESTNET EXEC - GUARDED] Would place (capped preview): {}", preview)
            if len(to_add) > 5:
                logger.info("[TESTNET EXEC - GUARDED] Additional adds suppressed in preview: {}", len(to_add) - 5)
            if to_remove:
                logger.info("[TESTNET EXEC - GUARDED] Would cancel {} intents (dry-run preview)", len(to_remove))

        self._last_desired = desired_orders


def _normalize(orders: List[Dict]) -> List[Dict]:
    """
    Normalize orders to a comparable structure. For scaffolding, compare by
    (pair, side, spread, size_quote) only.
    """
    norm: List[Dict] = []
    for o in orders or []:
        norm.append(
            {
                "pair": o.get("pair"),
                "side": o.get("side"),
                "spread": float(o.get("spread", 0.0)),
                "size_quote": float(o.get("size_quote", 0.0)),
            }
        )
    return norm
