"""Phase 7 -- paper-trading performance dashboard.

Compares the system's paper P&L against simply buying SPY on each alert date,
over the same windows. Reports cumulative return vs SPY, win rate, average R,
and current open positions. Prints the capital-deployment reminder.

R is defined per trade as realized_return / entry-risk, where entry-risk is the
distance from reference price down to the entry-zone low (the structural stop).
"""
import datetime as dt

import numpy as np

from backtest import data_cache
from journal import tracker


def _spy_return(start_iso, end_iso):
    spy = data_cache.get("SPY", period="3y")
    if spy is None or spy.empty:
        return None
    try:
        s = dt.date.fromisoformat(start_iso)
        e = dt.date.fromisoformat(end_iso)
    except (TypeError, ValueError):
        return None
    si = spy.index[spy.index >= str(s)]
    ei = spy.index[spy.index >= str(e)]
    if len(si) == 0 or len(ei) == 0:
        return None
    return float(spy.loc[ei[0], "close"] / spy.loc[si[0], "close"] - 1)


def _trade_R(rec):
    ref = rec.get("reference_price")
    ez = rec.get("entry_zone") or [None, None]
    if not ref or ez[0] is None:
        return None
    risk = (ref - ez[0]) / ref
    if risk <= 0:
        return None
    return rec["realized_return"] / risk


def build(records=None, pipeline_version=None):
    records = records if records is not None else tracker.all_alerts()
    if pipeline_version is not None:
        records = [r for r in records
                   if (r.get("pipeline_version") or 1) == pipeline_version]
    closed = [r for r in records if r.get("realized_return") is not None]
    open_ = [r for r in records if r["status"] == "open"]

    rets = np.array([r["realized_return"] for r in closed]) if closed else np.array([])
    cum = float(np.prod(1 + rets) - 1) if len(rets) else 0.0

    spy_rets = []
    for r in closed:
        sr = _spy_return(r["issued"], r.get("resolved_on") or r["issued"])
        if sr is not None:
            spy_rets.append(sr)
    spy_cum = float(np.prod(1 + np.array(spy_rets)) - 1) if spy_rets else float("nan")

    Rs = [x for x in (_trade_R(r) for r in closed) if x is not None]

    return {
        "n_closed": len(closed),
        "n_open": len(open_),
        "win_rate": float((rets > 0).mean()) if len(rets) else 0.0,
        "cum_return": cum,
        "spy_cum_return": spy_cum,
        "excess_vs_spy": cum - spy_cum if spy_cum == spy_cum else float("nan"),
        "avg_R": float(np.mean(Rs)) if Rs else 0.0,
        "open_positions": [r["ticker"] for r in open_],
    }


def print_dashboard(records=None):
    d = build(records)
    bar = "=" * 64
    print(bar)
    print("  PAPER TRADING DASHBOARD (Alpaca paper / simulated)")
    print(bar)
    print(f"  Closed trades     : {d['n_closed']}")
    print(f"  Open positions    : {d['n_open']}  {d['open_positions']}")
    print(f"  Win rate          : {d['win_rate']*100:.1f}%")
    print(f"  Avg R             : {d['avg_R']:+.2f}")
    print(f"  Cumulative return : {d['cum_return']*100:+.2f}%")
    print(f"  SPY (same windows): {d['spy_cum_return']*100:+.2f}%")
    print(f"  Excess vs SPY     : {d['excess_vs_spy']*100:+.2f}%")
    all_recs = records if records is not None else tracker.all_alerts()
    versions = {(r.get("pipeline_version") or 1) for r in all_recs}
    if len(versions) > 1:
        for v in sorted(versions):
            dv = build(all_recs, pipeline_version=v)
            print(f"  V{v}: {dv['n_closed']} closed, win {dv['win_rate']*100:.0f}%, "
                  f"cum {dv['cum_return']*100:+.1f}% vs SPY {dv['spy_cum_return']*100:+.1f}%")
        print(bar)
    print("  REMINDER: do NOT move to real capital until paper results beat SPY")
    print("  after costs over the full 6-month validation window.")
    print(bar)
    return d


if __name__ == "__main__":
    print_dashboard()
