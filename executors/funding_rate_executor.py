"""
Funding rate monitoring and signal generation (Scaffold).
"""
from __future__ import annotations

from typing import Dict, List

from loguru import logger

from ..utils.hyperliquid_utils import HyperliquidClient


class FundingRateExecutor:
    def __init__(self, *, threshold: float, testnet: bool = False) -> None:
        self.threshold = threshold
        self._running = False
        self._client: HyperliquidClient | None = None
        self._testnet = testnet

    def start(self) -> None:
        logger.info("FundingRateExecutor started")
        self._running = True
        # Initialize client (read-only)
        self._client = HyperliquidClient(testnet=self._testnet)

    def stop(self) -> None:
        logger.info("FundingRateExecutor stopped")
        self._running = False
        self._client = None

    def get_signals(self, pairs: List[str]) -> Dict[str, float]:
        """
        Return a simple dict of pair -> funding bias signal.
        Positive => favor short; Negative => favor long.
        Uses a simple threshold; below threshold returns 0.0 bias.
        """
        if not self._running or self._client is None:
            return {p: 0.0 for p in pairs}

        signals: Dict[str, float] = {}
        for p in pairs:
            try:
                rate = float(self._client.get_funding_rate(p))
            except Exception as e:
                logger.debug("Funding fetch failed for {}: {}", p, e)
                rate = 0.0
            # Always log raw rate
            logger.info("Funding rate {} = {}", p, rate)
            bias = rate if abs(rate) >= self.threshold else 0.0
            signals[p] = bias
            logger.info("Funding bias {} = {} (threshold={})", p, bias, self.threshold)
        logger.debug("Funding signals: {}", signals)
        return signals
