"""Gate 2.5 -- macro tailwind/headwind.

Scores a stock's alignment with the macro factors its sector cares about
(10Y yield, dollar, oil, gold, semis). Boost tailwinds; penalize names fighting
their group's macro. Only HARD-rejects when fighting multiple factors at once.

`data` optional keys:
  sector: GICS sector string
  macro:  {macro_ticker: bars_df}
"""
from backtest import data_cache
from engine import fundamentals
from engine.sectors import MACRO_SENSITIVITY, MACRO_TICKERS
from engine.types import GateResult

_TREND_LOOKBACK = 21


def _factor_trend(bars):
    """+1 if the factor is rising over the lookback, -1 if falling, 0 if flat."""
    if bars is None or bars.empty or len(bars) <= _TREND_LOOKBACK:
        return 0
    cur = float(bars["close"].iloc[-1])
    prev = float(bars["close"].iloc[-1 - _TREND_LOOKBACK])
    if prev == 0:
        return 0
    chg = cur / prev - 1
    return 1 if chg > 0.01 else (-1 if chg < -0.01 else 0)


def check(ticker, data):
    sector = data.get("sector") or fundamentals.info(ticker).get("sector")
    sens = MACRO_SENSITIVITY.get(sector)
    if not sens:
        return GateResult(True, 5.0, f"Macro neutral: no mapping for sector '{sector}'.")

    macro = data.get("macro") or {}
    alignment = 0
    notes = []
    for factor, sign in sens.items():
        bars = macro.get(factor)
        if bars is None:
            bars = data_cache.get(factor, period="6mo")
        trend = _factor_trend(bars)
        contrib = sign * trend
        alignment += contrib
        if trend != 0:
            arrow = "up" if trend > 0 else "down"
            tag = "tailwind" if contrib > 0 else ("headwind" if contrib < 0 else "neutral")
            notes.append(f"{factor} {arrow} ({tag})")

    score = max(0.0, min(10.0, 5 + alignment * 1.5))
    passed = alignment > -2  # only reject when fighting 2+ factors
    detail = "; ".join(notes) if notes else "no notable macro moves"
    verdict = "tailwind" if alignment > 0 else ("headwind" if alignment < 0 else "neutral")
    reason = f"Macro {verdict} for {sector} (align {alignment:+d}): {detail}."
    if not passed:
        reason = f"Fighting macro: {sector} (align {alignment:+d}): {detail}."
    return GateResult(passed, round(score, 2), reason)
