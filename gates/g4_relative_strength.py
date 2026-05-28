"""Gate 4 -- relative strength.

PASS only if RS rating >= 80 (percentile of ~6-12M return vs the universe) AND
the stock outperforms its own sector ETF over 3 months.

`data` optional keys:
  rs_universe_returns: list of trailing returns for the whole universe (for the
                       percentile). If absent, the gate degrades to the sector
                       comparison alone.
  sector_etf_bars / sector: to compare vs the sector ETF.
"""
import numpy as np

from backtest import data_cache
from engine import fundamentals
from engine.sectors import etf_for_sector
from engine.types import GateResult

_RS_MIN = 80
_RS_LOOKBACK = 126  # ~6 months trading days


def _trailing_return(bars, lookback=_RS_LOOKBACK):
    if bars is None or len(bars) <= lookback:
        return None
    return float(bars["close"].iloc[-1] / bars["close"].iloc[-1 - lookback] - 1)


def check(ticker, data):
    bars = data.get("bars")
    own_ret = _trailing_return(bars)
    if own_ret is None:
        return GateResult(False, 0.0, f"{ticker}: insufficient history for RS.")

    # RS percentile vs universe.
    universe = data.get("rs_universe_returns")
    rs = None
    if universe:
        arr = np.asarray([r for r in universe if r is not None], dtype=float)
        if len(arr) >= 10:
            rs = float((arr < own_ret).mean() * 100)

    # Sector outperformance over 3M.
    sector = data.get("sector") or fundamentals.info(ticker).get("sector")
    etf = etf_for_sector(sector)
    sb = data.get("sector_etf_bars") or {}
    etf_bars = sb.get(etf)
    if etf_bars is None and etf:
        etf_bars = data_cache.get(etf, period="6mo")
    own_3m = _trailing_return(bars, 63)
    etf_3m = _trailing_return(etf_bars, 63) if etf_bars is not None else None
    beats_sector = (etf_3m is None) or (own_3m is not None and own_3m > etf_3m)

    if rs is None:
        # No universe -> fall back to sector comparison only.
        passed = beats_sector
        return GateResult(passed, 6.0 if passed else 3.0,
                          f"RS (no universe): 3M {own_3m*100:+.0f}% vs {etf} "
                          f"{(etf_3m*100 if etf_3m is not None else float('nan')):+.0f}% "
                          f"-> {'leads' if passed else 'lags'} sector.")

    passed = rs >= _RS_MIN and beats_sector
    score = round(min(10.0, rs / 10), 2)
    reason = (f"RS {rs:.0f} ( >= {_RS_MIN}? {'yes' if rs>=_RS_MIN else 'no'}), "
              f"3M {own_3m*100:+.0f}% vs {etf} -> "
              f"{'beats' if beats_sector else 'lags'} sector.")
    return GateResult(passed, score, reason)
