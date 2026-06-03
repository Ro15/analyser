"""Preview dry-run of the proposed HYBRID voting funnel on the live universe.

Runs the cheap guardrails (g1 liquidity, g5 setups) and cheap voters
(g2 trend, g2.5 macro, g3 sector, g4 rel-strength, g5.3 priced-in, g6 volume
flow) on every universe stock. Then runs the expensive guardrails (g5.5
valuation, g7 earnings blackout) on the top cheap-vote candidates. Reports
survivor counts at several vote thresholds.

Skips the LLM stage and the expensive voters (g5.7 fundamentals, g6.5 smart
money, g7.5 earnings quality) -- this is a fast preview, not the final hybrid.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import data_cache  # noqa: E402
from data.ingest import universe as universe_src  # noqa: E402
from engine.dataset import load_market  # noqa: E402
from engine.sectors import ALL_SECTOR_ETFS, MACRO_TICKERS  # noqa: E402
from gates import (g0_regime, g1_liquidity, g2_trend, g2_5_macro,  # noqa: E402
                   g3_sector, g4_relative_strength, g5_setups,
                   g5_3_priced_in, g5_5_valuation, g6_volume_flow,
                   g7_earnings_block)

# Hybrid config (cheap-only preview)
CHEAP_GUARDRAILS = [("g1_liquidity", g1_liquidity), ("g5_setups", g5_setups)]
CHEAP_VOTERS = [
    ("g2_trend",        g2_trend,            1.2),
    ("g2.5_macro",      g2_5_macro,          1.0),
    ("g3_sector",       g3_sector,           0.9),
    ("g4_rel_strength", g4_relative_strength, 1.2),
    ("g5.3_priced_in",  g5_3_priced_in,      1.0),
    ("g6_volume_flow",  g6_volume_flow,      1.0),
]
EXPENSIVE_GUARDRAILS = [("g5.5_valuation", g5_5_valuation),
                        ("g7_earnings_block", g7_earnings_block)]
THRESHOLDS = [3.0, 4.0, 4.5, 5.0, 5.5, 6.0]


def main():
    t0 = time.time()
    universe = universe_src.get_universe()
    print(f"[hybrid-dryrun] {len(universe)} stocks in universe", flush=True)

    market = load_market()
    regime = g0_regime.check("MARKET", market)
    print(f"Gate 0 regime: {'PASS' if regime.passed else 'FAIL'} -- {regime.reasoning}",
          flush=True)
    if not regime.passed:
        return

    sector_etf_bars = {e: data_cache.get(e, period="1y", max_age_hours=18)
                       for e in ALL_SECTOR_ETFS}
    macro = {m: data_cache.get(m, period="6mo", max_age_hours=18)
             for m in MACRO_TICKERS}
    sector_by_t = universe_src.load_sector_map()

    data_cache.prefetch_bulk(universe, period="3y")  # uses cache if fresh

    bars_by_t = {}
    rs_returns = []
    for t in universe:
        df = data_cache.get(t, period="3y", max_age_hours=18)
        if df.empty:
            continue
        bars_by_t[t] = df
        if len(df) > 126:
            rs_returns.append(float(df["close"].iloc[-1] / df["close"].iloc[-127] - 1))
    print(f"[hybrid-dryrun] {len(bars_by_t)} stocks with bars (prep: {time.time()-t0:.0f}s)",
          flush=True)

    cheap_reject_at = {label: 0 for label, _ in CHEAP_GUARDRAILS}
    scored = []  # (ticker, weighted_vote, scores_dict)

    for t, bars in bars_by_t.items():
        data = {
            "bars": bars,
            "vix": market["vix"], "spx": market["spx"],
            "sector": sector_by_t.get(t),
            "macro": macro,
            "sector_etf_bars": sector_etf_bars,
            "rs_universe_returns": rs_returns,
        }
        rejected = False
        for label, gate in CHEAP_GUARDRAILS:
            r = gate.check(t, data)
            if not r.passed:
                cheap_reject_at[label] += 1
                rejected = True
                break
        if rejected:
            continue

        scores = {}
        wsum = wden = 0.0
        for label, gate, w in CHEAP_VOTERS:
            r = gate.check(t, data)
            scores[label] = r.score
            wsum += w * r.score
            wden += w
        vote = wsum / wden if wden else 0.0
        scored.append((t, vote, scores))

    print(f"[hybrid-dryrun] cheap stage done in {time.time()-t0:.0f}s. "
          f"Rejected by guardrails: {cheap_reject_at}", flush=True)
    print(f"[hybrid-dryrun] {len(scored)} stocks made it through cheap stage to vote",
          flush=True)

    print("\nSurvivor count by VOTE THRESHOLD (cheap voters only, no expensive checks yet):")
    print(f"{'threshold':>10}  {'count':>6}  {'% of universe':>12}")
    for thr in THRESHOLDS:
        n = sum(1 for _, v, _ in scored if v >= thr)
        print(f"   >= {thr:.1f}    {n:>6}     {100*n/len(universe):>5.1f}%")

    scored.sort(key=lambda x: x[1], reverse=True)
    print(f"\nTOP 25 by cheap-vote score:")
    print(f"{'#':>3}  {'ticker':<6}  {'vote':>5}   sector")
    for i, (t, v, _) in enumerate(scored[:25], 1):
        print(f"{i:>3}  {t:<6}  {v:>5.2f}   {sector_by_t.get(t, '?')}")

    # Now check expensive guardrails on the top N candidates above default threshold
    threshold = 5.0
    candidates = [(t, v, sc) for t, v, sc in scored if v >= threshold]
    n_check = min(len(candidates), 100)
    print(f"\n[hybrid-dryrun] running expensive guardrails "
          f"(valuation + earnings-blackout) on top {n_check} candidates...", flush=True)

    exp_t = time.time()
    final = []
    exp_reject_at = {label: 0 for label, _ in EXPENSIVE_GUARDRAILS}
    for t, vote, scores in candidates[:n_check]:
        data = {
            "bars": bars_by_t[t],
            "vix": market["vix"], "spx": market["spx"],
            "sector": sector_by_t.get(t),
            "macro": macro,
            "sector_etf_bars": sector_etf_bars,
            "rs_universe_returns": rs_returns,
        }
        rejected = False
        for label, gate in EXPENSIVE_GUARDRAILS:
            r = gate.check(t, data)
            if not r.passed:
                exp_reject_at[label] += 1
                rejected = True
                break
        if not rejected:
            final.append((t, vote))
    print(f"[hybrid-dryrun] expensive stage done in {time.time()-exp_t:.0f}s. "
          f"Rejected by: {exp_reject_at}", flush=True)

    print(f"\n=== FINAL HYBRID SURVIVORS (threshold {threshold}, of top {n_check}): "
          f"{len(final)} ===")
    for i, (t, v) in enumerate(final[:30], 1):
        print(f"  {i:>2}  {t:<6}  vote {v:>5.2f}   {sector_by_t.get(t, '?')}")

    print(f"\n[hybrid-dryrun] total elapsed: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
