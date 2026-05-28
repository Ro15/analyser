"""Gate 5 -- setup detection.

Detects three entry setups and returns which matched + a quality score 0-10:
  (a) pullback to a rising 50-day MA
  (b) VCP -- volatility contraction (tightening range + drying volume)
  (c) base breakout on above-average volume

GateResult.reasoning names the matched setup(s); score is the best quality found.
"""
import numpy as np

from engine.config import load_config
from engine.indicators import atr, ma_slope, sma
from engine.types import GateResult


def _pullback(bars, cfg):
    """(a) Price within proximity of a rising 50DMA, after a prior advance."""
    close = bars["close"]
    ma = sma(close, cfg["pullback_ma_days"])
    if ma.isna().iloc[-1]:
        return 0.0, None
    price = float(close.iloc[-1])
    ma_now = float(ma.iloc[-1])
    slope = ma_slope(ma, 21)
    if slope is None or slope != slope or slope <= 0:
        return 0.0, None
    dist = abs(price / ma_now - 1)
    if dist > cfg["pullback_proximity_pct"]:
        return 0.0, None
    # Prior advance: price up over the last ~3 months.
    if len(close) > 63 and close.iloc[-1] <= close.iloc[-63]:
        return 0.0, None
    # Tighter to the MA + steeper slope == better.
    quality = 6 + (1 - dist / cfg["pullback_proximity_pct"]) * 2 + min(2, slope * 100)
    return round(min(10.0, quality), 2), (
        f"pullback to rising 50DMA (${ma_now:.2f}, {dist*100:.1f}% away)"
    )


def _vcp(bars, cfg):
    """(b) Volatility contraction: recent range + volume tighter than earlier."""
    n = cfg["vcp_lookback"]
    if len(bars) < n:
        return 0.0, None
    window = bars.iloc[-n:]
    half = n // 2
    early, late = window.iloc[:half], window.iloc[half:]

    def rng(w):
        return float((w["high"].max() - w["low"].min()) / w["close"].mean())

    early_r, late_r = rng(early), rng(late)
    if early_r <= 0:
        return 0.0, None
    contraction = 1 - late_r / early_r  # >0 means range tightened
    vol_dry = early["volume"].mean() > 0 and (
        late["volume"].mean() < early["volume"].mean()
    )
    # Must still be in an uptrend (above rising 50DMA) and meaningfully tighter.
    ma = sma(bars["close"], 50)
    above = float(bars["close"].iloc[-1]) > float(ma.iloc[-1]) if not ma.isna().iloc[-1] else False
    if contraction < 0.15 or not above:
        return 0.0, None
    quality = 5 + contraction * 8 + (1.0 if vol_dry else 0.0)
    return round(min(10.0, quality), 2), (
        f"VCP contraction {contraction*100:.0f}%"
        f"{' + volume drying' if vol_dry else ''}"
    )


def _breakout(bars, cfg):
    """(c) Close breaks above the prior N-day high on above-average volume."""
    n = cfg["breakout_lookback"]
    if len(bars) < n + 1:
        return 0.0, None
    close = bars["close"]
    prior_high = float(bars["high"].iloc[-(n + 1):-1].max())
    price = float(close.iloc[-1])
    if price <= prior_high:
        return 0.0, None
    avg_vol = float(bars["volume"].iloc[-(n + 1):-1].mean())
    vol = float(bars["volume"].iloc[-1])
    if avg_vol <= 0 or vol < avg_vol * cfg["breakout_volume_mult"]:
        return 0.0, None
    vmult = vol / avg_vol
    ext = (price / prior_high - 1) * 100
    quality = 6 + min(2.5, (vmult - cfg["breakout_volume_mult"])) + min(1.5, ext)
    return round(min(10.0, quality), 2), (
        f"breakout +{ext:.1f}% over {n}d high on {vmult:.1f}x volume"
    )


def check(ticker, data):
    cfg = load_config()["setups"]
    bars = data.get("bars")
    if bars is None or len(bars) < cfg["breakout_lookback"] + 2:
        return GateResult(False, 0.0, f"{ticker}: insufficient history for setups.")

    candidates = [
        _pullback(bars, cfg),
        _vcp(bars, cfg),
        _breakout(bars, cfg),
    ]
    matched = [(q, desc) for q, desc in candidates if q > 0 and desc]

    if not matched:
        return GateResult(False, 0.0, "No setup matched (pullback / VCP / breakout).")

    best_q = max(q for q, _ in matched)
    descs = "; ".join(desc for _, desc in sorted(matched, reverse=True))
    return GateResult(True, best_q, f"Setup: {descs}.")
