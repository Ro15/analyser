"""Gate 7 -- earnings blackout.

REJECT if earnings fall within the next ~10 days (binary event risk too close to
entry). FLAG (but pass) earnings dates inside the 90-day hold window so the
structuring/exit logic can plan around them.
"""
import datetime as dt

import pandas as pd

from engine import fundamentals
from engine.types import GateResult

_BLOCK_DAYS = 10
_HOLD_DAYS = 90


def _next_earnings(ticker, data):
    ed = data.get("earnings_dates")
    if ed is None:
        ed = fundamentals.earnings_dates(ticker)
    if ed is None or len(ed) == 0:
        return None
    today = pd.Timestamp.now(tz=ed.index.tz) if ed.index.tz else pd.Timestamp.now()
    future = ed.index[ed.index >= today]
    return future.min() if len(future) else None


def check(ticker, data):
    nxt = _next_earnings(ticker, data)
    if nxt is None:
        return GateResult(True, 5.0, "Earnings date unknown -> pass (cannot block).")

    days = (nxt.date() - dt.date.today()).days
    if days <= _BLOCK_DAYS:
        return GateResult(False, 0.0,
                          f"Earnings in {days}d (<= {_BLOCK_DAYS}d) -> blackout, reject.")
    in_window = days <= _HOLD_DAYS
    flag = f" -- INSIDE 90d hold window (plan exit around {nxt.date()})" if in_window else ""
    return GateResult(True, 8.0 if not in_window else 6.0,
                      f"Earnings in {days}d ({nxt.date()}){flag}.")
