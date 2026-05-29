"""Manually rebuild the scan universe now (instead of waiting for the weekly
auto-refresh). Reads price/liquidity floors from config.yaml.

Run: ./venv/bin/python scripts/build_universe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.ingest import universe as U  # noqa: E402
from engine.config import load_config  # noqa: E402


def main():
    cfg = load_config()
    rows = U.build(min_price=cfg.get("min_price", 5),
                   min_dollar_volume=cfg.get("liquidity_min_dollar_volume", 5_000_000))
    U.save(rows)
    print(f"rebuilt universe: {len(rows)} stocks")
    print("by sector:")
    for sector, n in U.sector_breakdown(rows).items():
        print(f"  {sector:<26} {n}")


if __name__ == "__main__":
    main()
