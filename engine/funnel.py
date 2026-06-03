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
from data.ingest import universe as universe_src
from engine.config import load_config
from journal import tuner
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


def _prefetch_context(universe, period, max_age_hours=data_cache.LIVE_MAX_AGE_HOURS):
    """Shared, computed-once context: market, sector ETFs, macro, RS universe.

    `max_age_hours` keeps a live scan on fresh prices (refresh anything older);
    the market series (^VIX/^GSPC) is always fetched fresh in load_market.
    """
    market = load_market()
    sector_etf_bars = {e: data_cache.get(e, period="1y", max_age_hours=max_age_hours)
                       for e in ALL_SECTOR_ETFS}
    macro = {m: data_cache.get(m, period="6mo", max_age_hours=max_age_hours)
             for m in MACRO_TICKERS}

    data_cache.prefetch_bulk(universe, period=period, max_age_hours=max_age_hours)

    bars_by_ticker, rs_returns = {}, []
    for t in universe:
        df = data_cache.get(t, period=period, max_age_hours=max_age_hours)
        if df.empty:
            continue
        bars_by_ticker[t] = df
        if len(df) > 126:
            rs_returns.append(float(df["close"].iloc[-1] / df["close"].iloc[-127] - 1))
    return market, sector_etf_bars, macro, bars_by_ticker, rs_returns


def run(universe=None, period="3y", top_n=15, verbose=True):
    cfg = load_config()
    if universe is None:
        universe = universe_src.get_universe()

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

    # ---- Hybrid voting setup: guardrails block, voters get a weighted vote ----
    funnel_cfg = cfg.get("funnel") or {}
    guardrails = set(funnel_cfg.get("guardrails", []))
    voter_set = set(funnel_cfg.get("voters", []))
    threshold = funnel_cfg.get("vote_threshold", 5.0)
    weights = tuner.effective_weights(funnel_cfg.get("default_weights", {}))

    rejections = {label: [] for label, _ in CHAIN}
    rejections["vote_threshold"] = []   # synthetic bucket for "vote too low"
    survivors = []
    # Sector comes from the universe metadata (the screener), so the cheap
    # technical gates never trigger a per-stock fundamentals fetch. The
    # fundamental gates (g5.5+) self-fetch fundamentals.info on demand, so only
    # names that survive the cheap filters ever pay that cost.
    sector_by_ticker = universe_src.load_sector_map()

    for t, bars in bars_by_ticker.items():
        data = {
            "bars": bars,
            "vix": market["vix"], "spx": market["spx"],
            "sector": sector_by_ticker.get(t),
            "macro": macro,
            "sector_etf_bars": sector_etf_bars,
            "rs_universe_returns": rs_returns,
        }
        scores, reasonings = {}, {}
        guardrail_failed = None
        for label, gate in CHAIN:
            res = gate.check(t, data)
            scores[label] = res.score
            reasonings[label] = res.reasoning
            if label in guardrails and not res.passed:
                rejections[label].append(t)
                guardrail_failed = (label, res.reasoning)
                log.info("BLOCK %s at %s: %s", t, label, res.reasoning)
                break
            # voters: never break -- their `passed` is informational, score counts

        if guardrail_failed:
            continue

        # Weighted vote across the voter gates that scored this ticker.
        wsum, wden = 0.0, 0.0
        for label in voter_set:
            if label in scores:
                w = weights.get(label, 1.0)
                wsum += w * scores[label]
                wden += w
        vote = wsum / wden if wden else 0.0

        if vote < threshold:
            rejections["vote_threshold"].append(t)
            log.info("REJECT %s vote %.2f < %.2f", t, vote, threshold)
            continue

        survivors.append({"ticker": t, "scores": scores,
                          "reasonings": reasonings,
                          "vote": round(vote, 2),
                          "total": round(sum(scores.values()), 1),
                          "sector": data["sector"],
                          "_data": data})

    # ---- Phase 4: boost survivors with a scheduled catalyst in the hold window ----
    hold = cfg["backtest"]["hold_days"]
    for s in survivors:
        cat = calendar_db.best_in_window(s["ticker"], hold_days=hold)
        s["catalyst"] = cat
        if cat:
            s["scores"]["catalyst"] = cat["boost"]
            s["total"] = round(s["total"] + cat["boost"], 1)

    # Rank by the weighted vote first; catalyst boost is a tiebreaker on top.
    survivors.sort(key=lambda s: (s["vote"], s.get("scores", {}).get("catalyst", 0)),
                   reverse=True)
    if verbose:
        _print_summary(universe, rejections, survivors, top_n)
    return {"regime": regime, "survivors": survivors[:top_n],
            "all_survivors": survivors, "rejections": rejections}


def run_llm_stage(survivors, top=None, with_propagation=True, verbose=True):
    """Phase-5 LLM layer on the final survivors: news (8), sentiment (8.5),
    veteran review (9), plus propagation (8.3). Runs only on `max_finalists`.

    With no API keys, gates degrade to neutral passes (or run on LLM_MOCK=1).
    Returns {"finalists": [...], "propagated": {ticker: reason}}.
    """
    from data.ingest import news_multi
    from gates import (g8_news_catalyst, g8_3_propagation, g8_5_sentiment,
                       g9_veteran_review)

    cfg = load_config()["llm"]
    finalists = survivors[: top or cfg["max_finalists"]]
    out = []
    for s in finalists:
        t = s["ticker"]
        d = dict(s.get("_data", {}))
        headlines = news_multi.gather(t)  # free multi-source headlines for g8
        if headlines:
            d["headlines"] = headlines
        news = g8_news_catalyst.check(t, d)
        sentiment = g8_5_sentiment.check(t, d)
        vet_data = {**d, "gate_scores": s["scores"], "catalyst": s.get("catalyst"),
                    "setup": s.get("reasonings", {}).get("g5_setups"),
                    "news_summary": news.reasoning}
        veteran = g9_veteran_review.check(t, vet_data)
        llm_passed = news.passed and veteran.passed
        out.append({"ticker": t, "total": s["total"], "sector": s.get("sector"),
                    "catalyst": s.get("catalyst"),
                    "news": news, "sentiment": sentiment, "veteran": veteran,
                    "llm_passed": llm_passed})

    propagated = {}
    if with_propagation:
        cat_finalists = [(s["ticker"], s["catalyst"]["type"])
                         for s in finalists if s.get("catalyst")]
        propagated = g8_3_propagation.propagate(cat_finalists)

    if verbose:
        print(f"\n[funnel] LLM stage on {len(finalists)} finalists "
              f"(mock={__import__('os').getenv('LLM_MOCK')=='1'}):")
        for r in out:
            v = "PASS" if r["llm_passed"] else "REJECT"
            print(f"  [{v}] {r['ticker']:<6} news: {r['news'].reasoning}")
            print(f"          veteran: {r['veteran'].reasoning}")
            print(f"          {r['sentiment'].reasoning}")
        if propagated:
            print("  Read-through candidates added by propagation:")
            for tk, why in propagated.items():
                print(f"    {tk}: {why}")
    return {"finalists": out, "propagated": propagated}


def _print_summary(universe, rejections, survivors, top_n):
    print(f"\n[funnel] {len(universe)} in -> {len(survivors)} survivors")
    print("  Rejections by gate:")
    for label, _ in CHAIN:
        n = len(rejections.get(label, []))
        if n:
            print(f"    {label:<24} -{n}")
    n_vote = len(rejections.get("vote_threshold", []))
    if n_vote:
        print(f"    {'vote_threshold':<24} -{n_vote}")
    print(f"\n  Nightly top {min(top_n, len(survivors))} candidates:")
    print(f"  {'#':>2}  {'ticker':<6} {'vote':>5}  {'sector':<22} catalyst")
    for i, s in enumerate(survivors[:top_n], 1):
        cat = s.get("catalyst")
        cat_txt = (f"{cat['type']} in {cat['days_out']}d" if cat else "-- none in window")
        print(f"  {i:>2}  {s['ticker']:<6} {s.get('vote', 0):>5.2f}  "
              f"{str(s['sector'] or '?'):<22} {cat_txt}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run()
