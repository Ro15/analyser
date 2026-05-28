"""Gate 2 -- trend.

PASS if price is above a RISING 200-day MA, OR in a tight low-volatility base
after a prior uptrend (price near a flat-to-rising 200DMA with low ATR).
REJECT if price is below a DECLINING 200-day MA.
"""
from engine.config import load_config
from engine.indicators import atr, ma_slope, sma
from engine.types import GateResult


def check(ticker, data):
    cfg = load_config()["trend"]
    bars = data.get("bars")
    if bars is None or len(bars) < cfg["ma_days"] + cfg["ma_slope_lookback"]:
        return GateResult(False, 0.0, f"{ticker}: insufficient history for trend.")

    close = bars["close"]
    price = float(close.iloc[-1])
    ma = sma(close, cfg["ma_days"])
    ma_now = float(ma.iloc[-1])
    slope = ma_slope(ma, cfg["ma_slope_lookback"])  # fractional change
    atr_pct = float(atr(bars).iloc[-1] / price)

    above_ma = price > ma_now
    rising = slope is not None and slope == slope and slope > 0
    declining = slope is not None and slope == slope and slope < -0.005  # >0.5% drop
    tight_base = atr_pct <= cfg["base_max_atr_pct"]

    # REJECT: below a declining 200DMA.
    if (not above_ma) and declining:
        return GateResult(
            False, 0.0,
            f"Downtrend: price ${price:.2f} < falling 200DMA ${ma_now:.2f} "
            f"(slope {slope*100:+.1f}%).",
        )

    # PASS A: above a rising 200DMA.
    if above_ma and rising:
        ext = (price / ma_now - 1) * 100
        score = round(min(10.0, 6 + slope * 100 + max(0, 2 - ext / 10)), 2)
        return GateResult(
            True, score,
            f"Uptrend: price ${price:.2f} > rising 200DMA ${ma_now:.2f} "
            f"(slope {slope*100:+.1f}%, {ext:+.1f}% extended).",
        )

    # PASS B: tight low-vol base after an uptrend (flat/rising MA, low ATR, near MA).
    if tight_base and not declining and price >= ma_now * 0.97:
        return GateResult(
            True, 6.0,
            f"Tight base: price ${price:.2f} near 200DMA ${ma_now:.2f}, "
            f"ATR {atr_pct*100:.1f}% (low-vol), MA slope {slope*100:+.1f}%.",
        )

    # Everything else: not a clean uptrend, not an outright downtrend -> reject.
    return GateResult(
        False, 2.0,
        f"No clean uptrend: price ${price:.2f} vs 200DMA ${ma_now:.2f} "
        f"(slope {slope*100:+.1f}%, ATR {atr_pct*100:.1f}%).",
    )
