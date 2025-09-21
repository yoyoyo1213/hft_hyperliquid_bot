def test_imports():
    # Smoke test to ensure modules import
    import importlib

    modules = [
        "controllers.pmm_funding_arb_controller",
        "controllers.risk_manager",
        "executors.funding_rate_executor",
        "executors.position_executor",
        "utils.hyperliquid_utils",
        "utils.performance_tracker",
    ]

    for m in modules:
        importlib.import_module(m)
