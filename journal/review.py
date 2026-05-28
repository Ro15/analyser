"""Periodic journal review: win-rate breakdown by setup, sector, regime,
conviction, and signal combination."""
from collections import defaultdict

from journal import tracker


def _agg(records, keyfn):
    buckets = defaultdict(lambda: {"n": 0, "wins": 0, "ret": 0.0})
    for r in records:
        if r.get("realized_return") is None:
            continue
        k = keyfn(r)
        b = buckets[k]
        b["n"] += 1
        b["wins"] += 1 if r["realized_return"] > 0 else 0
        b["ret"] += r["realized_return"]
    return {k: {"n": b["n"],
                "win_rate": round(b["wins"] / b["n"], 3) if b["n"] else 0.0,
                "avg_return": round(b["ret"] / b["n"], 4) if b["n"] else 0.0}
            for k, b in buckets.items()}


def breakdown(records=None):
    records = records if records is not None else tracker.all_alerts()
    closed = [r for r in records if r.get("realized_return") is not None]
    return {
        "n_closed": len(closed),
        "by_setup": _agg(closed, lambda r: r.get("setup") or "?"),
        "by_sector": _agg(closed, lambda r: r.get("sector") or "?"),
        "by_regime": _agg(closed, lambda r: r.get("regime") or "?"),
        "by_conviction": _agg(closed, lambda r: f"conv{r.get('conviction')}"),
        "by_catalyst_type": _agg(
            closed, lambda r: (r.get("catalyst") or {}).get("type") or "none"),
    }


def print_review(records=None):
    b = breakdown(records)
    print(f"Journal review — {b['n_closed']} closed trades")
    for dim in ("by_setup", "by_sector", "by_regime", "by_conviction", "by_catalyst_type"):
        print(f"\n  {dim}:")
        for k, v in sorted(b[dim].items(), key=lambda kv: kv[1]["avg_return"], reverse=True):
            print(f"    {k:<22} n={v['n']:<3} win {v['win_rate']*100:4.0f}%  "
                  f"avg {v['avg_return']*100:+.1f}%")
    return b


if __name__ == "__main__":
    print_review()
