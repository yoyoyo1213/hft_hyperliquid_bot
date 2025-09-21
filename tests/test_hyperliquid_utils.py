import sys
from pathlib import Path
import unittest
from unittest.mock import patch

# Ensure the repository root is on sys.path so 'hft_hyperliquid_bot' can be imported
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from hft_hyperliquid_bot.utils.hyperliquid_utils import HyperliquidClient


class TestHyperliquidUtils(unittest.TestCase):
    def setUp(self):
        self.client = HyperliquidClient()

    @patch.object(HyperliquidClient, "_post_info")
    def test_resolve_coin_uses_universe(self, mock_post):
        # metaAndAssetCtxs shape: [ {"universe": [{"name": "UBTC"}, {"name": "ETH"}]}, ctxs ]
        mock_post.return_value = [
            {"universe": [{"name": "UBTC"}, {"name": "ETH"}]},
            [{"funding": "0.0"}, {"funding": "0.0"}],
        ]
        coin_btc = self.client.resolve_coin("BTC-USDC")
        coin_eth = self.client.resolve_coin("ETH-USDC")
        self.assertEqual(coin_btc, "UBTC")
        self.assertEqual(coin_eth, "ETH")

    @patch.object(HyperliquidClient, "_post_info")
    def test_get_funding_rate_parses_from_ctxs(self, mock_post):
        mock_post.return_value = [
            {"universe": [{"name": "BTC"}, {"name": "SOL"}]},
            [{"funding": "0.0000125"}, {"funding": "-0.0000456"}],
        ]
        rate_btc = self.client.get_funding_rate("BTC-USDC")
        rate_sol = self.client.get_funding_rate("SOL-USDC")
        self.assertAlmostEqual(rate_btc, 0.0000125)
        self.assertAlmostEqual(rate_sol, -0.0000456)

    @patch.object(HyperliquidClient, "_post_info")
    def test_get_orderbook_normalizes_levels(self, mock_post):
        mock_post.return_value = {
            "levels": [
                [{"px": 100.0, "sz": 2.0}, {"px": 99.5, "sz": 1.0}],
                [{"px": 100.5, "sz": 2.5}, {"px": 101.0, "sz": 3.0}],
            ]
        }
        ob = self.client.get_orderbook("BTC-USDC")
        self.assertIn("bids", ob)
        self.assertIn("asks", ob)
        self.assertEqual(ob["bids"][0], [100.0, 2.0])
        self.assertEqual(ob["asks"][0], [100.5, 2.5])


if __name__ == "__main__":
    unittest.main()
