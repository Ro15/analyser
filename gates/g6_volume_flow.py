"""Gate 6 -- volume / flow accumulation signature.

PASS when up-volume exceeds down-volume and OBV is rising. REJECT setups
forming on DECLINING volume (no demand confirmation).
"""
from engine.indicators import obv
from engine.types import GateResult

_LOOKBACK = 50


def check(ticker, data):
    bars = data.get("bars")
    if bars is None or len(bars) < _LOOKBACK + 1:
        return GateResult(False, 0.0, f"{ticker}: insufficient history for flow.")

    w = bars.iloc[-_LOOKBACK:]
    chg = w["close"].diff()
    up_vol = float(w["volume"][chg > 0].sum())
    down_vol = float(w["volume"][chg < 0].sum())
    ratio = up_vol / down_vol if down_vol > 0 else float("inf")

    ob = obv(bars)
    obv_rising = float(ob.iloc[-1]) > float(ob.iloc[-_LOOKBACK])

    # Volume trend: recent half vs earlier half of the window.
    half = _LOOKBACK // 2
    recent_v = float(w["volume"].iloc[-half:].mean())
    earlier_v = float(w["volume"].iloc[:half].mean())
    declining = recent_v < earlier_v * 0.8

    if declining and not obv_rising:
        return GateResult(False, 2.0,
                          f"Distribution/dry: volume falling ({recent_v/earlier_v:.0%} of prior), "
                          f"OBV not rising. No demand confirmation.")

    accumulation = ratio >= 1.0 and obv_rising
    score = round(min(10.0, 5 + (min(ratio, 3) - 1) * 2 + (1 if obv_rising else -2)), 2)
    score = max(0.0, score)
    if accumulation:
        return GateResult(True, score,
                          f"Accumulation: up/down vol {ratio:.2f}, OBV rising.")
    return GateResult(False, score,
                      f"No accumulation: up/down vol {ratio:.2f}, "
                      f"OBV {'rising' if obv_rising else 'flat/falling'}.")
