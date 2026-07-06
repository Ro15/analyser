"""One-off live smoke test of every openbb_source fetcher (network required).
Run: ./venv/bin/python scripts/obb_smoke.py [TICKER]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from data.ingest import openbb_source as obs

t = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
for name, fn in [("short_volume", obs.short_volume),
                 ("short_interest", obs.short_interest),
                 ("options_snapshot", obs.options_snapshot),
                 ("insider_activity", obs.insider_activity),
                 ("analyst_consensus", obs.analyst_consensus)]:
    out = fn(t)
    print(f"{'OK  ' if out is not None else 'FAIL'} {name}: {str(out)[:120]}")
