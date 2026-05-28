"""Forward catalyst calendar.

Merges two sources per ticker:
  1) earnings dates  -- pulled dynamically from yfinance
  2) seeded events   -- PDUFA / analyst day / product launch / index rebalance /
                        lockup expiry, from catalyst/seed_catalysts.yaml (extensible)

The "ideal window" for this bot is a catalyst 2-8 weeks out; `in_window` /
`best_in_window` support boosting such names in the funnel.
"""
import datetime as dt
import functools
import os

import pandas as pd
import yaml

from engine import fundamentals

_SEED_PATH = os.path.join(os.path.dirname(__file__), "seed_catalysts.yaml")

IDEAL_MIN_DAYS = 14
IDEAL_MAX_DAYS = 56  # ~8 weeks


@functools.lru_cache(maxsize=1)
def _seed():
    try:
        with open(_SEED_PATH) as f:
            return (yaml.safe_load(f) or {}).get("seed", {}) or {}
    except FileNotFoundError:
        return {}


def _earnings_events(ticker):
    ed = fundamentals.earnings_dates(ticker)
    if ed is None or len(ed) == 0:
        return []
    out = []
    for ts in ed.index:
        d = pd.Timestamp(ts).date()
        out.append({"date": d, "type": "earnings", "description": "Quarterly earnings"})
    return out


def get_catalysts(ticker):
    """All known catalysts (past + future) for a ticker, sorted by date."""
    events = list(_earnings_events(ticker))
    for e in _seed().get(ticker.upper(), []):
        d = e["date"]
        if isinstance(d, str):
            d = dt.date.fromisoformat(d)
        events.append({"date": d, "type": e.get("type", "other"),
                       "description": e.get("description", "")})
    return sorted(events, key=lambda e: e["date"])


def upcoming(ticker, within_days=90, today=None):
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=within_days)
    return [e for e in get_catalysts(ticker) if today <= e["date"] <= horizon]


def best_in_window(ticker, hold_days=90, today=None):
    """Return the most relevant upcoming catalyst inside the hold window + a
    boost score (peaks for catalysts in the 2-8 week ideal window)."""
    today = today or dt.date.today()
    ups = upcoming(ticker, within_days=hold_days, today=today)
    if not ups:
        return None
    # Prefer non-earnings catalysts (more asymmetric), else nearest event.
    ups.sort(key=lambda e: (e["type"] == "earnings", e["date"]))
    chosen = ups[0]
    days = (chosen["date"] - today).days
    if IDEAL_MIN_DAYS <= days <= IDEAL_MAX_DAYS:
        boost = 5.0
    elif days < IDEAL_MIN_DAYS:
        boost = 2.0   # very soon -> less anticipation runway
    else:
        boost = 3.0   # in window but far
    return {"date": chosen["date"], "type": chosen["type"],
            "description": chosen["description"], "days_out": days, "boost": boost}
