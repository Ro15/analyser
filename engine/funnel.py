"""Deterministic funnel: runs gates in funnel order, logging survivors and the
rejection reason at each gate. Cheap filters run first; expensive
fundamental/EDGAR gates run only on names that survive the technicals.

Gate 0 (regime) is system-level: if it fails, the whole night is a no-go.

This module covers the NON-LLM chain (Phases 1-3). LLM gates (8, 8.3, 9) and
structuring/correlation (10, 9.5) attach in later phases via run_llm_stage.
"""
import logging

from backtest import data_cache
from catalyst import calendar_db
from data.ingest.sp500 import get_sp500_tickers
from engine import fundamentals
from engine.config import load_config
from engine.dataset import load_market
from engine.indicators import sma
from engine.sectors import ALL_SECTOR_ETFS, MACRO_TICKERS
from gates import (
    g0_regime, g1_liquidity, g2_trend, g2_5_macro, g3_sector,
    g4_relative_strength, g5_setups, g5_3_priced_in, g5_5_valuation,
    g5_7_fundamentals, g6_volume_flow, g6_5_smart_money,
    g7_earnings_block, g7_5_earnings_quality,
)

log = logging.getLogger("funnel")

# Ordered per-ticker chain (cheap -> expensive). (label, module)
CHAIN = [
    ("g1_liquidity", g1_liquidity),
    ("g2_trend", g2_trend),
    ("g2.5_macro", g2_5_macro),
    ("g3_sector", g3_sector),
    ("g4_rel_strength", g4_relative_strength),
    ("g5_setups", g5_setups),
    ("g5.3_priced_in", g5_3_priced_in),
    ("g5.5_valuation", g5_5_valuation),
    ("g5.7_fundamentals", g5_7_fundamentals),
    ("g6_volume_flow", g6_volume_flow),
    ("g6.5_smart_money", g6_5_smart_money),
    ("g7_earnings_block", g7_earnings_block),
    ("g7.5_earnings_quality", g7_5_earnings_quality),
]


def _prefetch_context(universe, period):
    """Shared, computed-once context: market, sector ETFs, macro, RS universe."""
    market = load_market()
    sector_etf_bars = {e: data_cache.get(e, period="1y") for e in ALL_SECTOR_ETFS}
    macro = {m: data_cache.get(m, period="6mo") for m in MACRO_TICKERS}

    bars_by_ticker, rs_returns = {}, []
    for t in universe:
        df = data_cache.get(t, period=period)
        if df.empty:
            continue
        bars_by_ticker[t] = df
        if len(df) > 126:
            rs_returns.append(float(df["close"].iloc[-1] / df["close"].iloc[-127] - 1))
    return market, sector_etf_bars, macro, bars_by_ticker, rs_returns


def run(universe=None, period="3y", top_n=15, verbose=True):
    cfg = load_config()
    if universe is None:
        universe = get_sp500_tickers()[: cfg["backtest"]["universe_size"]]

    market, sector_etf_bars, macro, bars_by_ticker, rs_returns = _prefetch_context(
        universe, period
    )

    # ---- Gate 0: system-level regime ----
    regime = g0_regime.check("MARKET", market)
    if verbose:
        print(f"[funnel] Gate 0 regime: {'PASS' if regime.passed else 'FAIL'} "
              f"-- {regime.reasoning}")
    if not regime.passed:
        return {"regime": regime, "survivors": [], "rejections": {"g0_regime": list(universe)}}

    rejections = {label: [] for label, _ in CHAIN}
    survivors = []

    for t, bars in bars_by_ticker.items():
        info = fundamentals.info(t)
        data = {
            "bars": bars,
            "vix": market["vix"], "spx": market["spx"],
            "sector": info.get("sector"),
            "info": info,
            "macro": macro,
            "sector_etf_bars": sector_etf_bars,
            "rs_universe_returns": rs_returns,
        }
        scores = {}
        rejected_at = None
        for label, gate in CHAIN:
            res = gate.check(t, data)
            scores[label] = res.score
            if not res.passed:
                rejections[label].append(t)
                rejected_at = (label, res.reasoning)
                log.info("REJECT %s at %s: %s", t, label, res.reasoning)
                break
        if rejected_at is None:
            survivors.append({"ticker": t, "scores": scores,
                              "total": round(sum(scores.values()), 1),
                              "sector": info.get("sector")})

    # ---- Phase 4: boost survivors with a scheduled catalyst in the hold window ----
    hold = cfg["backtest"]["hold_days"]
    for s in survivors:
        cat = calendar_db.best_in_window(s["ticker"], hold_days=hold)
        s["catalyst"] = cat
        if cat:
            s["scores"]["catalyst"] = cat["boost"]
            s["total"] = round(s["total"] + cat["boost"], 1)

    survivors.sort(key=lambda s: s["total"], reverse=True)
    if verbose:
        _print_summary(universe, rejections, survivors, top_n)
    return {"regime": regime, "survivors": survivors[:top_n],
            "all_survivors": survivors, "rejections": rejections}


def _print_summary(universe, rejections, survivors, top_n):
    print(f"\n[funnel] {len(universe)} in -> {len(survivors)} survivors")
    print("  Rejections by gate:")
    for label, _ in CHAIN:
        n = len(rejections[label])
        if n:
            print(f"    {label:<24} -{n}")
    print(f"\n  Nightly top {min(top_n, len(survivors))} candidates:")
    print(f"  {'#':>2}  {'ticker':<6} {'total':>6}  {'sector':<22} catalyst")
    for i, s in enumerate(survivors[:top_n], 1):
        cat = s.get("catalyst")
        cat_txt = (f"{cat['type']} in {cat['days_out']}d" if cat else "-- none in window")
        print(f"  {i:>2}  {s['ticker']:<6} {s['total']:>6.1f}  "
              f"{str(s['sector'] or '?'):<22} {cat_txt}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run()
