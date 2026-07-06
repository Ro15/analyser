"""Human-readable backtest report. Always prints the survivorship-bias warning."""
from backtest.metrics import compute_metrics

_BAR = "=" * 72


def print_report(df):
    m = compute_metrics(df)
    print()
    print(_BAR)
    print("  BACKTEST REPORT -- core gates (0,1,2,5)")
    print(_BAR)

    # CLAUDE.md guardrail: this warning must always print.
    print("  !! SURVIVORSHIP BIAS WARNING !!")
    print("  Universe = CURRENT S&P 500 membership (yfinance has no point-in-time")
    print("  index data). Delisted/removed names never appear, so these results are")
    print("  OPTIMISTIC and overstate the true edge. Treat as an upper bound.")
    print(_BAR)

    # V2 guardrail: these signals have no free history, so the replay can't
    # include them -- paper trading is their only validation.
    print("  V2 NOTE: options-flow / short-volume / insider gates are NOT in")
    print("  this replay (no free history); validated in paper trading only.")
    print(_BAR)

    if m["alerts"] == 0:
        print("  No alerts generated -- nothing to evaluate.")
        print(_BAR)
        return m

    spy = m["avg_spy_return"]
    excess = m["avg_excess_vs_spy"]
    print(f"  Simulated alerts        : {m['alerts']}")
    print(f"  Win rate (% positive)   : {m['win_rate']*100:5.1f}%")
    print(f"  % reaching +15% (MFE)   : {m['hit_target_rate']*100:5.1f}%")
    print(f"  Avg return / pick       : {m['avg_return']*100:+5.2f}%")
    print(f"  Median return / pick    : {m['median_return']*100:+5.2f}%")
    print(f"  Avg SPY (same windows)  : {spy*100:+5.2f}%")
    print(f"  Avg EXCESS vs SPY       : {excess*100:+5.2f}%   <-- the number that matters")
    print(f"  % of picks beating SPY  : {m['pct_beating_spy']*100:5.1f}%")
    print(f"  Worst pick (max DD)     : {m['max_drawdown_per_pick']*100:+5.2f}%")
    print(f"  Best pick               : {m['best_pick']*100:+5.2f}%")
    print(f"  Sharpe-like (per-trade) : {m['sharpe_like']:.3f}")
    print(_BAR)

    verdict = "BEATS SPY" if excess > 0 else "DOES NOT beat SPY"
    print(f"  GO/NO-GO: strategy {verdict} after costs (avg excess {excess*100:+.2f}%).")
    if excess <= 0:
        print("  -> Edge not demonstrated. Fix gates before building further (per CLAUDE.md).")
    else:
        print("  -> Edge present in-sample, BUT remember survivorship bias inflates this.")
    print(_BAR)
    print()
    return m
