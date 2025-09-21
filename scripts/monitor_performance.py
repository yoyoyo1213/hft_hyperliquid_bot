"""
Simple monitoring scaffold. Extend with real dashboards/alerts.
"""
from __future__ import annotations

from time import sleep
from loguru import logger


def main() -> None:
    logger.info("Monitoring (stub)... press Ctrl+C to exit.")
    try:
        while True:
            # In the future, query performance snapshots and print KPIs
            sleep(10)
    except KeyboardInterrupt:
        logger.info("Monitor stopped")


if __name__ == "__main__":
    main()
