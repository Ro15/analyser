"""Gate 8.5 -- contrarian sentiment guard (LOW-WEIGHT, NOISY).

Reduces conviction when retail looks euphoric (protects against buying tops).
A true implementation would use Google Trends + social sentiment; to stay
key-free and deterministic we use a price/volume euphoria proxy:
  - sharp recent run-up (parabolic)
  - volume blow-off (recent volume >> baseline)
  - stretched above the 50-day MA
This is explicitly marked noisy and never hard-rejects on its own.
"""
from engine.indicators import sma
from engine.types import GateResult


def check(ticker, data):
    bars = data.get("bars")
    if bars is None or len(bars) < 60:
        return GateResult(True, 5.0, "Sentiment: insufficient data -> neutral (noisy).")

    c = bars["close"]
    runup_1m = float(c.iloc[-1] / c.iloc[-21] - 1)
    ma50 = sma(c, 50).iloc[-1]
    stretch = float(c.iloc[-1] / ma50 - 1) if ma50 == ma50 else 0.0
    vol_recent = float(bars["volume"].iloc[-5:].mean())
    vol_base = float(bars["volume"].iloc[-60:-5].mean())
    vol_spike = vol_recent / vol_base if vol_base > 0 else 1.0

    euphoria = 0
    notes = []
    if runup_1m > 0.20:
        euphoria += 1; notes.append(f"+{runup_1m*100:.0f}% 1mo")
    if stretch > 0.15:
        euphoria += 1; notes.append(f"{stretch*100:.0f}% above 50DMA")
    if vol_spike > 2.0:
        euphoria += 1; notes.append(f"{vol_spike:.1f}x volume blow-off")

    # Score is a conviction MULTIPLIER signal (5 = neutral). Lower when euphoric.
    score = round(max(2.0, 5.0 - euphoria * 1.5), 2)
    detail = "; ".join(notes) if notes else "no euphoria signals"
    return GateResult(True, score,
                      f"[noisy/low-weight] Contrarian: euphoria {euphoria}/3 ({detail}).")
