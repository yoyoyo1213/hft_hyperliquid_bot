"""
Risk management utilities for HFT strategy (Scaffold).
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from loguru import logger


class RiskManager:
    def __init__(
        self,
        *,
        stop_loss: float,
        take_profit: float,
        max_position_size: float,
        max_drawdown: float,
        cooldown_time: int,
        per_pair_max_quote: Optional[Dict[str, float]] = None,
    ) -> None:
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_position_size = max_position_size
        self.max_drawdown = max_drawdown
        self.cooldown_time = cooldown_time
        # Per-pair exposure caps (quote currency)
        self._per_pair_cap: Dict[str, float] = per_pair_max_quote or {}
        # State for circuit breaker / cooldown
        self._last_loss_ts: float = 0.0
        self._equity_peak: Optional[float] = None
        self._equity_now: Optional[float] = None

    def filter_orders(self, desired_orders: List[Dict]) -> List[Dict]:
        """
        Apply basic sizing constraints. If in cooldown or circuit breaker is
        active due to drawdown, block all new orders.
        """
        if self.should_pause_after_loss():
            logger.warning("Risk pause active due to recent loss. Blocking new orders for {}s.", self.cooldown_time)
            return []
        if self.breached_drawdown():
            logger.error("Circuit breaker triggered: max_drawdown {} breached. Blocking orders.", self.max_drawdown)
            return []

        filtered: List[Dict] = []
        used_by_pair: Dict[str, float] = {}
        audit: Dict[str, Dict[str, float]] = {}
        capped_count = 0
        skipped_count = 0
        for o in desired_orders:
            pair = str(o.get("pair"))
            size = min(float(o.get("size_quote", 0.0)), self.max_position_size)
            if size <= 0:
                continue
            # Enforce per-pair cap if configured
            cap = self._per_pair_cap.get(pair)
            if cap is not None:
                used = used_by_pair.get(pair, 0.0)
                remaining = max(0.0, cap - used)
                if remaining <= 0.0:
                    logger.warning("Per-pair cap reached for {} (cap={}). Skipping order.", pair, cap)
                    skipped_count += 1
                    audit[pair] = {"used": used, "cap": cap, "remaining": 0.0}
                    continue
                if size > remaining:
                    logger.warning(
                        "Per-pair cap would be exceeded for {}. Capping size {} -> {}.",
                        pair,
                        size,
                        remaining,
                    )
                    size = remaining
                    capped_count += 1
                used_by_pair[pair] = used + size
                audit[pair] = {"used": used_by_pair[pair], "cap": cap, "remaining": max(0.0, cap - used_by_pair[pair])}
            filtered.append({**o, "size_quote": size})
        # Per-cycle cap audit summary
        if self._per_pair_cap:
            # Ensure all capped pairs appear in audit
            for pair, cap in self._per_pair_cap.items():
                if pair not in audit:
                    used = used_by_pair.get(pair, 0.0)
                    audit[pair] = {"used": used, "cap": cap, "remaining": max(0.0, cap - used)}
            logger.info("Cap audit: {} | cappedOrders={} skippedOrders={}", audit, capped_count, skipped_count)
        return filtered

    # --- Triple-barrier scaffolds ---
    def compute_barriers(self, entry_px: float) -> Dict[str, float]:
        """
        Given an entry price, compute stop-loss and take-profit absolute price
        levels based on configured percentages. Time barrier is represented by
        cooldown_time for now (scaffold).
        """
        if entry_px <= 0:
            return {"stop_loss_px": 0.0, "take_profit_px": 0.0}
        sl = entry_px * (1.0 - self.stop_loss)
        tp = entry_px * (1.0 + self.take_profit)
        return {"stop_loss_px": sl, "take_profit_px": tp}

    def record_fill(self, pnl_delta: float) -> None:
        """
        Record a realized PnL delta. If negative, activate cooldown timer.
        """
        if pnl_delta < 0:
            self._last_loss_ts = time.time()
            logger.warning("Recorded loss {:.6f}. Cooldown initiated for {}s.", pnl_delta, self.cooldown_time)

    def update_equity(self, equity: float) -> None:
        """
        Update current equity and maintain peak to evaluate drawdown.
        """
        self._equity_now = equity
        if self._equity_peak is None or equity > self._equity_peak:
            self._equity_peak = equity

    # --- Controls ---
    def should_pause_after_loss(self) -> bool:
        if self._last_loss_ts <= 0:
            return False
        return (time.time() - self._last_loss_ts) < self.cooldown_time

    def breached_drawdown(self) -> bool:
        if self._equity_peak is None or self._equity_now is None:
            return False
        if self._equity_peak <= 0:
            return False
        dd = 1.0 - (self._equity_now / self._equity_peak)
        return dd >= self.max_drawdown
