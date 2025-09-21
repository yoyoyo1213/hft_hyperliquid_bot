"""
PMM Funding Arbitrage Controller (Scaffold)

Implements a PMM Simple V2 style market making loop with funding-aware adjustments.
This is a scaffold: exchange wiring is abstracted via utils.hyperliquid_utils.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Dict, List, Optional

from loguru import logger
from pydantic import BaseModel

from ..controllers.risk_manager import RiskManager
from ..executors.funding_rate_executor import FundingRateExecutor
from ..executors.position_executor import PositionExecutor
from ..utils.hyperliquid_utils import HyperliquidClient


class StrategyConfig(BaseModel):
    connector_name: str = "hyperliquid_perpetual"
    trading_pairs: List[str] = ["BTC-USDC", "ETH-USDC", "SOL-USDC"]
    leverage: int = 3
    total_amount_quote: float = 10000.0
    position_mode: str = "one_way"
    executor_refresh_time: int = 30
    cooldown_time: int = 300
    # Execution/network flags
    network: str = "mainnet"  # "mainnet" or "testnet"
    dry_run: bool = True
    # Per-pair exposure caps (quote currency, e.g., USDC)
    per_pair_max_quote: Dict[str, float] = {}

    # Spread configuration
    buy_spreads: List[float] = [0.0001, 0.0002, 0.0005]
    sell_spreads: List[float] = [0.0001, 0.0002, 0.0005]
    order_levels: int = 3
    order_refresh_time: int = 10

    # Risk controls
    stop_loss: float = 0.002
    take_profit: float = 0.001
    max_position_size: float = 5000
    max_drawdown: float = 0.05
    funding_rate_threshold: float = 0.0001


@dataclass
class ControllerState:
    running: bool = False
    cooldown_until: Optional[float] = None


class PMMFundingArbController:
    """Main controller orchestrating funding, position executors, and risk."""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.state = ControllerState()
        self.risk = RiskManager(
            stop_loss=self.config.stop_loss,
            take_profit=self.config.take_profit,
            max_position_size=self.config.max_position_size,
            max_drawdown=self.config.max_drawdown,
            cooldown_time=self.config.cooldown_time,
            per_pair_max_quote=self.config.per_pair_max_quote,
        )
        self.funding_exec = FundingRateExecutor(
            threshold=self.config.funding_rate_threshold,
            testnet=(self.config.network.lower() == "testnet"),
        )
        self.position_exec = PositionExecutor(
            connector_name=self.config.connector_name,
            leverage=self.config.leverage,
            position_mode=self.config.position_mode,
            dry_run=self.config.dry_run,
            testnet=(self.config.network.lower() == "testnet"),
        )
        # Market data client for health snapshots
        self._market_client = HyperliquidClient(
            testnet=(self.config.network.lower() == "testnet")
        )
        self._tick_count = 0
        # Equity tracking (scaffold). Start from total_amount_quote.
        self._equity: float = float(self.config.total_amount_quote)

    def start(self) -> None:
        logger.info(
            "Starting PMMFundingArbController | network={} dry_run={}",
            self.config.network,
            self.config.dry_run,
        )
        self.state.running = True
        self.funding_exec.start()
        self.position_exec.start()
        # Log resolved coin mappings for clarity (e.g., BTC -> UBTC)
        try:
            client = HyperliquidClient()
            mappings = []
            for pair in self.config.trading_pairs:
                coin = client.resolve_coin(pair)
                mappings.append(f"{pair} -> {coin}")
            logger.info("Resolved coin mappings: {}", mappings)
            # One-time startup fetch: funding and top-of-book for each pair
            for pair in self.config.trading_pairs:
                coin = client.resolve_coin(pair)
                try:
                    fr = client.get_funding_rate(pair)
                except Exception as e:
                    logger.debug("Startup funding fetch failed for {}: {}", pair, e)
                    fr = 0.0
                try:
                    ob = client.get_orderbook(pair)
                    bids = ob.get("bids", [])
                    asks = ob.get("asks", [])
                    best_bid = bids[0] if bids else None
                    best_ask = asks[0] if asks else None
                except Exception as e:
                    logger.debug("Startup orderbook fetch failed for {}: {}", pair, e)
                    best_bid = None
                    best_ask = None
                logger.info(
                    "Startup summary {} (coin={}): fundingRate={}, bestBid={}, bestAsk={}",
                    pair,
                    coin,
                    fr,
                    best_bid,
                    best_ask,
                )
        except Exception as e:
            logger.debug("Failed to resolve coin mappings: {}", e)

    def stop(self) -> None:
        logger.info("Stopping PMMFundingArbController")
        self.state.running = False
        self.funding_exec.stop()
        self.position_exec.stop()

    def on_tick(self) -> None:
        """Single control loop tick. Wire into a scheduler/loop with refresh time."""
        if not self.state.running:
            return

        # 1) Pull market data snapshot and funding signal (stubbed)
        funding_signals = self.funding_exec.get_signals(self.config.trading_pairs)

        # 2) Compute desired orders based on PMM spreads and funding bias
        desired_orders = self._compute_desired_orders(funding_signals)

        # 3) Apply risk controls
        desired_orders = self.risk.filter_orders(desired_orders)

        # 4) Submit to position executor
        self.position_exec.sync_orders(desired_orders)

        # 5) Periodic health snapshot: mid-price and depth metrics of first pair
        try:
            self._tick_count += 1
            if self._tick_count % 2 == 0 and self.config.trading_pairs:
                idx = (self._tick_count // 2) % len(self.config.trading_pairs)
                pair = self.config.trading_pairs[idx]
                ob = self._market_client.get_orderbook(pair)
                bids = ob.get("bids", [])
                asks = ob.get("asks", [])
                best_bid = bids[0][0] if bids else None
                best_ask = asks[0][0] if asks else None
                if best_bid is not None and best_ask is not None:
                    mid = (best_bid + best_ask) / 2.0
                else:
                    mid = None
                # Depth metrics (top-5 cumulative size)
                bid_depth5 = sum([float(lvl[1]) for lvl in bids[:5]]) if bids else 0.0
                ask_depth5 = sum([float(lvl[1]) for lvl in asks[:5]]) if asks else 0.0
                spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
                logger.info(
                    "Health: {} bestBid={} bestAsk={} mid={} spread={} bidDepth5={} "
                    "askDepth5={} bidLevels={} askLevels={}",
                    pair,
                    best_bid,
                    best_ask,
                    mid,
                    spread,
                    bid_depth5,
                    ask_depth5,
                    len(bids) if bids else 0,
                    len(asks) if asks else 0,
                )
        except Exception as e:
            logger.debug("Health snapshot failed: {}", e)

        # 6) Simulate tiny PnL based on funding bias to exercise RiskManager
        try:
            if funding_signals:
                avg_bias = mean([float(v) for v in funding_signals.values()])
                # Scale to be extremely small relative change
                pnl_delta = avg_bias * (self.config.total_amount_quote * 1e-4)
            else:
                pnl_delta = 0.0
            self._equity += pnl_delta
            if pnl_delta < 0:
                self.risk.record_fill(pnl_delta)
            self.risk.update_equity(self._equity)
            # Log risk status
            equity_peak = getattr(self.risk, "_equity_peak", None)
            dd_pct = 0.0
            if equity_peak:
                dd_pct = max(0.0, (1.0 - (self._equity / equity_peak)) * 100.0)
            logger.info(
                "Equity status: equity={:.2f} peak={} drawdown={:.4f}% cooldownActive={}",
                self._equity,
                equity_peak,
                dd_pct,
                self.risk.should_pause_after_loss(),
            )
        except Exception as e:
            logger.debug("Equity update failed: {}", e)

    def _compute_desired_orders(self, funding_signals: Dict[str, float]) -> List[Dict]:
        """
        Build a list of desired orders per pair using configured spreads and optional
        funding bias (e.g., tilt inventory or skew spreads).
        """
        orders: List[Dict] = []
        for pair in self.config.trading_pairs:
            bias = funding_signals.get(pair, 0.0)
            # Simple skew: if funding > 0, prefer short-side slightly by widening buy spread
            buy_spreads = [s * (1 + max(0.0, bias)) for s in self.config.buy_spreads]
            sell_spreads = [s * (1 + max(0.0, -bias)) for s in self.config.sell_spreads]

            for i in range(self.config.order_levels):
                orders.append(
                    {
                        "pair": pair,
                        "side": "buy",
                        "spread": buy_spreads[i],
                        "size_quote": self._per_level_quote_allocation(pair),
                    }
                )
                orders.append(
                    {
                        "pair": pair,
                        "side": "sell",
                        "spread": sell_spreads[i],
                        "size_quote": self._per_level_quote_allocation(pair),
                    }
                )
        return orders

    def _per_level_quote_allocation(self, pair: str) -> float:
        # Simple equal allocation across pairs and levels for scaffold
        pairs = max(1, len(self.config.trading_pairs))
        levels = max(1, self.config.order_levels * 2)  # buy+sell
        return self.config.total_amount_quote / (pairs * levels)
