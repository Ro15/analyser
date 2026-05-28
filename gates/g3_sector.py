"""Gate 3 -- sector rotation.

Ranks the 11 sector ETFs by blended 1M/3M momentum; passes only names whose
sector is in the top 4. Override: a stock with exceptional individual 3M
strength (>= override_3m) passes even from a weak sector.

`data` optional keys:
  sector: GICS sector string
  sector_etf_bars: {etf: bars_df}
  bars: the stock's own bars (for the override)
"""
from backtest import data_cache
from engine import fundamentals
from engine.sectors import ALL_SECTOR_ETFS, SECTOR_ETF, etf_for_sector
from engine.types import GateResult

_OVERRIDE_3M = 0.25  # +25% over 3M = exceptional individual strength


def _mom(bars):
    if bars is None or bars.empty or len(bars) < 63:
        return None
    c = bars["close"]
    m1 = float(c.iloc[-1] / c.iloc[-21] - 1)
    m3 = float(c.iloc[-1] / c.iloc[-63] - 1)
    return 0.5 * m1 + 0.5 * m3


def check(ticker, data):
    sector = data.get("sector") or fundamentals.info(ticker).get("sector")
    etf = etf_for_sector(sector)

    etf_bars = data.get("sector_etf_bars") or {}
    scores = {}
    for e in ALL_SECTOR_ETFS:
        b = etf_bars.get(e)
        if b is None:
            b = data_cache.get(e, period="6mo")
        m = _mom(b)
        if m is not None:
            scores[e] = m
    if not scores:
        return GateResult(True, 5.0, "Sector data unavailable -> neutral pass.")

    ranked = sorted(scores, key=scores.get, reverse=True)
    top4 = ranked[:4]
    rank = ranked.index(etf) + 1 if etf in ranked else None

    # Individual-strength override.
    own = data.get("bars")
    own_3m = None
    if own is not None and len(own) >= 63:
        own_3m = float(own["close"].iloc[-1] / own["close"].iloc[-63] - 1)

    if etf in top4:
        score = round(10 - (rank - 1) * 1.5, 2)
        return GateResult(True, score,
                          f"Sector {sector} ({etf}) ranks #{rank}/11 -> top-4 leader.")
    if own_3m is not None and own_3m >= _OVERRIDE_3M:
        return GateResult(True, 7.0,
                          f"Sector {sector} ({etf}) weak (#{rank}) but stock +{own_3m*100:.0f}% "
                          f"3M -> individual-strength override.")
    rank_txt = f"#{rank}/11" if rank else "unknown"
    return GateResult(False, 2.0,
                      f"Sector {sector} ({etf}) ranks {rank_txt}, outside top-4. Rejected.")
