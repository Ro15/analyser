"""Gate 5.3 -- "already priced in" detector.

If a stock has already run up >= run_up_max (default +10%) over the recent
window, the anticipated catalyst is likely already in the price -> REJECT.
Conviction is reduced proportionally to any run-up below that threshold.
"""
from engine.types import GateResult

_LOOKBACK = 21        # ~1 month
_RUNUP_MAX = 0.10     # +10% recent move = likely priced in


def check(ticker, data):
    bars = data.get("bars")
    if bars is None or len(bars) <= _LOOKBACK:
        return GateResult(False, 0.0, f"{ticker}: insufficient history.")

    c = bars["close"]
    runup = float(c.iloc[-1] / c.iloc[-1 - _LOOKBACK] - 1)

    if runup >= _RUNUP_MAX:
        return GateResult(False, 0.0,
                          f"Likely priced in: +{runup*100:.1f}% over {_LOOKBACK}d "
                          f">= +{_RUNUP_MAX*100:.0f}% threshold. Move may already be made.")

    # Below threshold: full score when flat/down, scaling down toward 0 near it.
    frac = max(0.0, runup) / _RUNUP_MAX
    score = round(10 * (1 - frac), 2)
    return GateResult(True, score,
                      f"Room to run: {runup*100:+.1f}% over {_LOOKBACK}d "
                      f"(< +{_RUNUP_MAX*100:.0f}%); conviction x{1-frac:.2f}.")
