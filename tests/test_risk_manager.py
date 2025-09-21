import sys
import time
import unittest
from pathlib import Path

# Ensure the repository root is on sys.path so 'hft_hyperliquid_bot' can be imported
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from hft_hyperliquid_bot.controllers.risk_manager import RiskManager  # noqa: E402


class TestRiskManager(unittest.TestCase):
    def make_rm(self, **overrides):
        params = dict(
            stop_loss=0.01,
            take_profit=0.02,
            max_position_size=100.0,
            max_drawdown=0.10,
            cooldown_time=1,  # short for test
            per_pair_max_quote={"BTC-USDC": 150.0},
        )
        params.update(overrides)
        return RiskManager(**params)

    def test_compute_barriers(self):
        rm = self.make_rm()
        b = rm.compute_barriers(100.0)
        self.assertAlmostEqual(b["stop_loss_px"], 99.0)
        self.assertAlmostEqual(b["take_profit_px"], 102.0)

    def test_cooldown_after_loss_blocks_orders_temporarily(self):
        rm = self.make_rm()
        # Record loss
        rm.record_fill(-1.0)
        # Should pause
        self.assertTrue(rm.should_pause_after_loss())
        # filter_orders returns [] while in cooldown
        out = rm.filter_orders([
            {"pair": "BTC-USDC", "size_quote": 50.0},
        ])
        self.assertEqual(out, [])
        # Wait a bit longer than cooldown
        time.sleep(1.1)
        self.assertFalse(rm.should_pause_after_loss())

    def test_drawdown_breach_triggers_circuit_breaker(self):
        rm = self.make_rm(max_drawdown=0.20)
        rm.update_equity(100.0)
        rm.update_equity(90.0)  # 10% dd -> below threshold
        self.assertFalse(rm.breached_drawdown())
        rm.update_equity(75.0)  # 25% dd -> breach
        self.assertTrue(rm.breached_drawdown())
        # Orders are blocked on breach
        out = rm.filter_orders([
            {"pair": "BTC-USDC", "size_quote": 50.0},
        ])
        self.assertEqual(out, [])

    def test_per_pair_caps_enforced(self):
        rm = self.make_rm(per_pair_max_quote={"BTC-USDC": 100.0})
        # Two orders that together exceed cap
        desired = [
            {"pair": "BTC-USDC", "size_quote": 80.0},
            {"pair": "BTC-USDC", "size_quote": 50.0},
        ]
        out = rm.filter_orders(desired)
        total = sum(o["size_quote"] for o in out)
        self.assertAlmostEqual(total, 100.0)
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[1]["size_quote"], 20.0)  # capped


if __name__ == "__main__":
    unittest.main()
