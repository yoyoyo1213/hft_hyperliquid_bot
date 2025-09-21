"""
Performance tracking primitives (Scaffold).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class PnLReport:
    realized: float = 0.0
    unrealized: float = 0.0
    fees: float = 0.0


class PerformanceTracker:
    def __init__(self) -> None:
        self.metrics: Dict[str, float] = {}

    def record_trade(self, pnl_delta: float) -> None:
        self.metrics["pnl"] = self.metrics.get("pnl", 0.0) + pnl_delta

    def snapshot(self) -> Dict[str, float]:
        return dict(self.metrics)
