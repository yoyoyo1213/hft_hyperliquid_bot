"""
Deploy the strategy using the scaffold controller.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from loguru import logger

try:
    # When executed as a module: python -m hft_hyperliquid_bot.scripts.deploy_strategy
    from ..controllers.pmm_funding_arb_controller import (
        PMMFundingArbController,
        StrategyConfig,
    )
except ImportError:
    # When executed directly: python scripts/deploy_strategy.py
    # Ensure the repository root (package parent) is on sys.path
    current_file = Path(__file__).resolve()
    package_root = current_file.parent.parent  # hft_hyperliquid_bot/
    repo_root = package_root.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from hft_hyperliquid_bot.controllers.pmm_funding_arb_controller import (
        PMMFundingArbController,
        StrategyConfig,
    )


def main() -> None:
    # Load environment variables from .env if present
    load_dotenv()
    # Configure file logging (rotating)
    try:
        # logs/ under project root (hft_hyperliquid_bot/)
        repo_root = Path(__file__).resolve().parents[1]
        logs_dir = repo_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "app.log"
        # Keep console logging and add file sink
        logger.add(
            str(log_path),
            rotation="10 MB",
            retention="10 days",
            compression="zip",
            enqueue=True,
            backtrace=False,
            diagnose=False,
            level="DEBUG",
        )
        logger.info("File logging enabled: {}", log_path)
    except Exception as e:
        logger.warning("Failed to configure file logging: {}", e)
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    config = StrategyConfig(**data)
    controller = PMMFundingArbController(config)

    controller.start()
    logger.info("Controller started. Press Ctrl+C to stop.")

    try:
        while True:
            controller.on_tick()
            time.sleep(config.executor_refresh_time)
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
