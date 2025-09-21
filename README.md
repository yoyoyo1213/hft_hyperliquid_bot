# HFT Hyperliquid Bot (Scaffold)

This repository is scaffolded from the saved spec `improved_hummingbot_hft_prompt.md` to build a production-ready HFT bot targeting Hyperliquid perpetuals using a PMM Simple V2 style controller with funding-rate enhancements.

## Structure

```
hft_hyperliquid_bot/
├── controllers/
│   ├── pmm_funding_arb_controller.py
│   └── risk_manager.py
├── executors/
│   ├── funding_rate_executor.py
│   └── position_executor.py
├── configs/
│   ├── production_config.yml
│   └── backtest_config.yml
├── utils/
│   ├── hyperliquid_utils.py
│   └── performance_tracker.py
├── scripts/
│   ├── deploy_strategy.py
│   └── monitor_performance.py
├── tests/
│   └── test_smoke.py
└── requirements.txt
```

## Quickstart

1. Create and activate a Python 3.10+ virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Adjust `configs/production_config.yml` for your pairs, spreads, and risk.
4. Run the (stub) deploy script:
   ```bash
   python scripts/deploy_strategy.py --config configs/production_config.yml
   ```

Note: This is an initial scaffold. Strategy wiring is designed to integrate with Hummingbot v2 components and a Hyperliquid connector, but actual exchange connectivity is stubbed pending environment setup and credentials.

## Next Steps

- Implement connector bindings in `utils/hyperliquid_utils.py`.
- Flesh out `controllers/pmm_funding_arb_controller.py` logic for order refresh and spread calc.
- Integrate risk controls from `controllers/risk_manager.py` in the execution flow.
- Add real funding subscription/handlers in `executors/funding_rate_executor.py`.
- Connect position management in `executors/position_executor.py` to live orders.
- Expand tests for controllers, executors, and risk logic.
