"""Gate 10 -- trade structuring.

Turns a finalist into a complete, actionable plan:
  - entry zone (around current price / nearest support)
  - the catalyst + its date
  - catalyst-INVALIDATION exit (the concrete way out -- a GUARDRAIL per CLAUDE.md)
  - +15% target with partial scale-out
  - time stop at catalyst date + buffer

Returns a plain dict so it serializes cleanly into alerts and the journal.
"""
import datetime as dt

from engine.config import load_config
from engine.indicators import atr, sma

_TARGET = 0.15
_TIME_BUFFER_DAYS = 10


def build_plan(ticker, data, catalyst=None, conviction=None, probability=None):
    bars = data.get("bars")
    if bars is None or bars.empty:
        return None
    price = float(bars["close"].iloc[-1])
    a = float(atr(bars).iloc[-1]) if len(bars) > 14 else price * 0.02
    ma50 = sma(bars["close"], 50).iloc[-1]
    support = float(ma50) if ma50 == ma50 else price - 2 * a

    entry_low = round(max(support, price - a), 2)
    entry_high = round(price + 0.5 * a, 2)
    target = round(price * (1 + _TARGET), 2)

    hold_days = load_config()["backtest"]["hold_days"]
    cat_date = catalyst.get("date") if catalyst else None
    if isinstance(cat_date, str):
        try:
            cat_date = dt.date.fromisoformat(cat_date)
        except ValueError:
            cat_date = None
    if cat_date:
        time_stop = cat_date + dt.timedelta(days=_TIME_BUFFER_DAYS)
    else:
        time_stop = dt.date.today() + dt.timedelta(days=hold_days)

    # Catalyst-invalidation exit: the concrete way out.
    invalidation = [
        "Exit if the catalyst is cancelled / indefinitely delayed.",
        "Exit if the catalyst event passes and the stock FADES (closes below the "
        f"entry zone low ${entry_low}) instead of running.",
        f"Hard structural stop: two consecutive closes below 50DMA (~${support:.2f}).",
    ]

    return {
        "ticker": ticker,
        "reference_price": round(price, 2),
        "entry_zone": [entry_low, entry_high],
        "catalyst": (None if not catalyst else
                     {"type": catalyst.get("type"),
                      "date": str(catalyst.get("date")),
                      "days_out": catalyst.get("days_out"),
                      "description": catalyst.get("description")}),
        "target": target,
        "target_pct": _TARGET,
        "scale_out": f"Sell 1/2 at +{int(_TARGET*100)}% (${target}); trail the "
                     f"remainder below the rising 50DMA.",
        "invalidation_exit": invalidation,
        "time_stop": str(time_stop),
        "conviction": conviction,
        "probability_15pct_90d": probability,
    }
