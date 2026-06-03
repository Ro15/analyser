"""Re-count hybrid survivors at a tighter vote threshold without re-fetching.

Uses only parquet bars already on disk (no yfinance fallback). Skips Gate 0
(we know the market is risk-on right now). Reports counts at thresholds
6.0/6.5/7.0/7.5/8.0 and lists the top hybrid survivors at threshold 7.0
including expensive-guardrail + a simulated correlation cap (2 per sector).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from backtest import data_cache  # noqa: E402
from data.ingest import universe as universe_src  # noqa: E402
from engine.sectors import ALL_SECTOR_ETFS, MACRO_TICKERS  # noqa: E402
from gates import (g1_liquidity, g2_trend, g2_5_macro, g3_sector,  # noqa: E402
                   g4_relative_strength, g5_setups, g5_3_priced_in,
                   g5_5_valuation, g6_volume_flow, g7_earnings_block)

CHEAP_GUARDRAILS = [("g1_liquidity", g1_liquidity), ("g5_setups", g5_setups)]
CHEAP_VOTERS = [
    ("g2_trend",        g2_trend,             1.2),
    ("g2.5_macro",      g2_5_macro,           1.0),
    ("g3_sector",       g3_sector,            0.9),
    ("g4_rel_strength", g4_relative_strength, 1.2),
    ("g5.3_priced_in",  g5_3_priced_in,       1.0),
    ("g6_volume_flow",  g6_volume_flow,       1.0),
]
EXP_GUARDRAILS = [("g5.5_valuation", g5_5_valuation),
                  ("g7_earnings_block", g7_earnings_block)]
THRESHOLDS = [5.0, 6.0, 6.5, 7.0, 7.5, 8.0]
SECTOR_CAP = 2  # mirrors g9.5 correlation filter's default max_per_sector


def cached(ticker, period="3y"):
    p = data_cache._path(ticker, period)
    if not os.path.exists(p):
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def main():
    t0 = time.time()
    universe = universe_src.get_universe()
    sector_by_t = universe_src.load_sector_map()

    sector_etf_bars = {e: cached(e, period="1y") for e in ALL_SECTOR_ETFS}
    macro = {m: cached(m, period="6mo") for m in MACRO_TICKERS}

    bars_by_t, rs_returns = {}, []
    for t in universe:
        df = cached(t)
        if df.empty:
            continue
        bars_by_t[t] = df
        if len(df) > 126:
            rs_returns.append(float(df["close"].iloc[-1] / df["close"].iloc[-127] - 1))
    print(f"{len(bars_by_t)} / {len(universe)} stocks with cached bars "
          f"(prep {time.time()-t0:.1f}s)", flush=True)

    scored = []
    for t, bars in bars_by_t.items():
        data = {
            "bars": bars,
            "sector": sector_by_t.get(t),
            "macro": macro,
            "sector_etf_bars": sector_etf_bars,
            "rs_universe_returns": rs_returns,
        }
        rejected = False
        for _, gate in CHEAP_GUARDRAILS:
            r = gate.check(t, data)
            if not r.passed:
                rejected = True
                break
        if rejected:
            continue
        wsum = wden = 0.0
        for _, gate, w in CHEAP_VOTERS:
            r = gate.check(t, data)
            wsum += w * r.score
            wden += w
        scored.append((t, wsum / wden if wden else 0.0))

    scored.sort(key=lambda x: x[1], reverse=True)
    print(f"\nVote-score distribution across {len(scored)} stocks "
          f"(after cheap guardrails):")
    print(f"{'threshold':>10}  {'count':>6}")
    for thr in THRESHOLDS:
        n = sum(1 for _, v in scored if v >= thr)
        print(f"   >= {thr:.1f}    {n:>6}")

    threshold = 7.0
    candidates = [(t, v) for t, v in scored if v >= threshold]
    print(f"\nRunning expensive guardrails (valuation + earnings) "
          f"on {len(candidates)} candidates >= {threshold}...", flush=True)
    final = []
    exp_rej = {label: 0 for label, _ in EXP_GUARDRAILS}
    for t, vote in candidates:
        data = {
            "bars": bars_by_t[t],
            "sector": sector_by_t.get(t),
            "macro": macro,
            "sector_etf_bars": sector_etf_bars,
            "rs_universe_returns": rs_returns,
        }
        rejected = False
        for label, gate in EXP_GUARDRAILS:
            r = gate.check(t, data)
            if not r.passed:
                exp_rej[label] += 1
                rejected = True
                break
        if not rejected:
            final.append((t, vote, sector_by_t.get(t, "?")))
    print(f"  expensive rejections: {exp_rej}")
    print(f"  passing all guardrails: {len(final)}")

    # Simulate correlation filter (sector cap = 2 per sector, in order of vote)
    final.sort(key=lambda x: x[1], reverse=True)
    sec_count, after_cap = {}, []
    for t, v, s in final:
        if sec_count.get(s, 0) >= SECTOR_CAP:
            continue
        sec_count[s] = sec_count.get(s, 0) + 1
        after_cap.append((t, v, s))

    print(f"\n=== FINAL HYBRID SHORTLIST (vote >= {threshold}, "
          f"safety guardrails passed, sector cap {SECTOR_CAP}) ===")
    print(f"{'#':>3}  {'ticker':<7} {'vote':>5}   sector")
    for i, (t, v, s) in enumerate(after_cap[:20], 1):
        print(f"{i:>3}  {t:<7} {v:>5.2f}   {s}")
    print(f"\n   {len(after_cap)} would feed the LLM stage")
    print(f"   With MAX_ALERTS=2  ->  ~{min(len(after_cap), 2)} alerts/night "
          f"(less if LLM rejects)")
    print(f"\ntotal elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
