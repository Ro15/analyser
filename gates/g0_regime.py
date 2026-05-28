"""Gate 0 -- market regime (system-level, not per-stock).

No alerts fire at all when the market is hostile:
  FAIL if VIX > vix_max  OR  S&P 500 is below its 200-day MA.
Breadth (% of S&P above its 50-day MA) is computed for context/scoring.

`data` dict keys:
  vix:   DataFrame of ^VIX bars (needs 'close')
  spx:   DataFrame of ^GSPC bars (needs 'close')
  breadth_pct: optional float 0-100, % of universe above its 50-day MA
"""
from engine.config import load_config
from engine.indicators import sma
from engine.types import GateResult


def check(ticker, data):
    cfg = load_config()["regime"]
    vix_df = data.get("vix")
    spx_df = data.get("spx")

    if vix_df is None or vix_df.empty or spx_df is None or spx_df.empty:
        return GateResult(False, 0.0, "Regime data unavailable (VIX/SPX missing).")

    vix = float(vix_df["close"].iloc[-1])
    spx_close = float(spx_df["close"].iloc[-1])
    spx_ma = sma(spx_df["close"], cfg["spx_ma_days"]).iloc[-1]

    if spx_ma is None or spx_ma != spx_ma:  # NaN guard (not enough history)
        return GateResult(False, 0.0, "Insufficient SPX history for 200-day MA.")
    spx_ma = float(spx_ma)

    vix_ok = vix <= cfg["vix_max"]
    spx_ok = spx_close > spx_ma

    breadth = data.get("breadth_pct")
    breadth_txt = f", breadth {breadth:.0f}% > 50DMA" if breadth is not None else ""

    passed = vix_ok and spx_ok
    # Score: calmer VIX + more SPX cushion + better breadth == higher.
    vix_score = max(0.0, 1 - vix / cfg["vix_max"])          # 0..1
    spx_cushion = max(-1.0, min(1.0, (spx_close / spx_ma - 1) * 10))  # ~+-10%
    spx_score = max(0.0, (spx_cushion + 1) / 2)             # 0..1
    breadth_score = (breadth / 100) if breadth is not None else 0.5
    score = round(10 * (0.4 * vix_score + 0.4 * spx_score + 0.2 * breadth_score), 2)

    if passed:
        reason = (
            f"Risk-ON: VIX {vix:.1f} <= {cfg['vix_max']}, "
            f"SPX {spx_close:.0f} > 200DMA {spx_ma:.0f}{breadth_txt}."
        )
    else:
        fails = []
        if not vix_ok:
            fails.append(f"VIX {vix:.1f} > {cfg['vix_max']}")
        if not spx_ok:
            fails.append(f"SPX {spx_close:.0f} < 200DMA {spx_ma:.0f}")
        reason = f"Risk-OFF: {'; '.join(fails)}{breadth_txt}. No alerts."
    return GateResult(passed, score, reason)
