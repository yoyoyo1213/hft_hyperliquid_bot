import sys
import unittest
from pathlib import Path

# Ensure the repository root is on sys.path so 'hft_hyperliquid_bot' can be imported
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from hft_hyperliquid_bot.executors.position_executor import PositionExecutor  # noqa: E402


class TestPositionExecutor(unittest.TestCase):
    def setUp(self):
        self.exec = PositionExecutor(
            connector_name="hyperliquid_perpetual",
            leverage=3,
            position_mode="one_way",
            dry_run=True,
            testnet=False,
        )
        self.exec.start()

    def tearDown(self):
        self.exec.stop()

    def test_sync_orders_tracks_last_desired(self):
        desired = [
            {"pair": "BTC-USDC", "side": "buy", "spread": 0.0001, "size_quote": 100.0},
            {"pair": "BTC-USDC", "side": "sell", "spread": 0.0001, "size_quote": 100.0},
        ]
        self.exec.sync_orders(desired)
        self.assertEqual(len(self.exec._last_desired), 2)

        # Second call with same desired should keep last_desired unchanged
        self.exec.sync_orders(desired)
        self.assertEqual(len(self.exec._last_desired), 2)

    def test_guarded_preview_path_does_not_error(self):
        # Switch to guarded path (still only preview logs; no real API)
        guarded = PositionExecutor(
            connector_name="hyperliquid_perpetual",
            leverage=1,
            position_mode="one_way",
            dry_run=False,
            testnet=True,
        )
        guarded.start()
        try:
            desired = [
                {"pair": "BTC-USDC", "side": "buy", "spread": 0.001, "size_quote": 50.0},
                {"pair": "BTC-USDC", "side": "sell", "spread": 0.001, "size_quote": 50.0},
            ]
            guarded.sync_orders(desired)
        finally:
            guarded.stop()


if __name__ == "__main__":
    unittest.main()
