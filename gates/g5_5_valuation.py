"""Gate 5.5 -- valuation ceiling (anti-FOMO GUARDRAIL, never remove).

Rejects names in the TOP DECILE of their own ~5-year valuation range.

DATA LIMITATION: yfinance has no point-in-time multiple history. We approximate
each stock's own valuation range two ways and reject if EITHER flags top-decile:
  1) current price's percentile within its trailing 5y price range (a P/S proxy,
     since shares outstanding are ~stable -> P/S tracks price), and
  2) current forward P/E / PEG / P/S / EV-EBITDA vs coarse absolute red lines.
This is intentionally conservative; documented as a proxy, not exact.
"""
from engine import fundamentals
from engine.types import GateResult

_TOP_DECILE = 0.90

# Coarse absolute "rich" red lines (sector-agnostic backstop).
_RICH = {"forwardPE": 60, "pegRatio": 3.0, "priceToSalesTrailing12Months": 20,
         "enterpriseToEbitda": 40}


def _price_percentile(bars):
    """Where the current price sits within its trailing 5y (or available) range."""
    if bars is None or len(bars) < 252:
        return None
    window = bars["close"].iloc[-min(len(bars), 252 * 5):]
    lo, hi = float(window.min()), float(window.max())
    if hi <= lo:
        return None
    return (float(window.iloc[-1]) - lo) / (hi - lo)


def check(ticker, data):
    bars = data.get("bars")
    pct = _price_percentile(bars)
    info = data.get("info") or fundamentals.info(ticker)

    rich_flags = []
    for k, limit in _RICH.items():
        v = info.get(k)
        if isinstance(v, (int, float)) and v > 0 and v > limit:
            rich_flags.append(f"{k} {v:.1f} > {limit}")

    # Primary guardrail: top-decile of own 5y price range (P/S proxy).
    if pct is not None and pct >= _TOP_DECILE:
        return GateResult(False, 0.0,
                          f"Anti-FOMO reject: price in top decile of 5y range "
                          f"(pctile {pct*100:.0f}%). Valuation likely stretched.")
    if len(rich_flags) >= 2:
        return GateResult(False, 0.0,
                          f"Anti-FOMO reject: rich multiples [{'; '.join(rich_flags)}].")

    if pct is None:
        return GateResult(True, 5.0,
                          "Valuation: insufficient price history for range proxy -> "
                          "neutral pass (treat with caution).")
    score = round(10 * (1 - pct), 2)  # cheaper within range -> higher score
    warn = f" (rich: {'; '.join(rich_flags)})" if rich_flags else ""
    return GateResult(True, score,
                      f"Valuation OK: price at {pct*100:.0f}% of 5y range "
                      f"(below top decile){warn}.")
