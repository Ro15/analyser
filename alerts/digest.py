"""V2 nightly digest: the ONE Telegram message you get every market night.

Sections: buy alerts (rare, +target% bar), watchlist near-misses (explicitly
NOT buy signals -- this is how "message every night" coexists with a high
bar), thesis-broken exits, and a one-line portfolio pulse."""
import datetime as dt

from backtest import data_cache
from engine.config import load_config
from journal import tracker


def portfolio_pulse():
    """One line: open count + avg P&L (vs SPY over the same windows) + closed avg."""
    opens = tracker.open_alerts()
    closed = [r for r in tracker.all_alerts()
              if r["status"] == "closed"
              and isinstance(r.get("realized_return"), (int, float))]
    parts = []
    if opens:
        rets, spy_rets = [], []
        spy = data_cache.get("SPY", period="1y")
        for r in opens:
            bars = data_cache.get(r["ticker"], period="1y")
            if bars is None or bars.empty:
                continue
            rets.append(float(bars["close"].iloc[-1]) / r["reference_price"] - 1)
            if spy is not None and not spy.empty:
                since = spy.index[spy.index >= r["issued"]]
                if len(since):
                    spy_rets.append(
                        float(spy["close"].iloc[-1] / spy.loc[since[0], "close"] - 1))
        if rets:
            line = f"{len(opens)} open avg {sum(rets)/len(rets)*100:+.1f}%"
            if spy_rets:
                line += f" (SPY same-dates {sum(spy_rets)/len(spy_rets)*100:+.1f}%)"
            parts.append(line)
    if closed:
        avg = sum(r["realized_return"] for r in closed) / len(closed)
        parts.append(f"{len(closed)} closed avg {avg*100:+.1f}%")
    return "; ".join(parts) or "no positions yet"


def _watch_line(f):
    deb = f.get("debate") or {}
    why = deb.get("reasoning") or ""
    p = deb.get("p_target_90d")
    ptxt = f"{p:.0%}" if isinstance(p, (int, float)) else "?"
    return (f"  • {f['ticker']}: conviction {deb.get('conviction', '?')}/10, "
            f"p(target) {ptxt} — {why[:120]}")


def build_digest(buys, watchlist, exits, pulse, shadow=False):
    cfg = load_config()
    target = int(float(cfg["backtest"]["target_pct"]) * 100)
    n_watch = int(cfg.get("digest", {}).get("watchlist_size", 3))
    today = dt.date.today().isoformat()

    lines = [f"🌙 *Nightly digest — {today}*" + (" [SHADOW]" if shadow else "")]

    if buys:
        lines.append(f"\n🟢 *Buy alerts (+{target}% / 90d bar):*")
        for b in buys:
            deb = b.get("debate") or {}
            p = deb.get("p_target_90d")
            ptxt = f"{p:.0%}" if isinstance(p, (int, float)) else "?"
            lines.append(f"  • {b['ticker']} — size {str(deb.get('size', '?')).upper()}, "
                         f"conviction {deb.get('conviction', '?')}/10, p {ptxt} "
                         f"(full plan follows)")
    else:
        lines.append(f"\n🟢 Buys: none cleared the +{target}% bar tonight — "
                     "that's the bar working, not a bug.")

    if watchlist:
        lines.append("\n👀 *Watchlist (NOT buy signals):*")
        lines.extend(_watch_line(f) for f in watchlist[:n_watch])

    if exits:
        lines.append("\n🏥 *Exit early:*")
        for e in exits:
            lines.append(f"  • {e['ticker']} ({e['return']*100:+.1f}%) — "
                         f"{(e.get('reason') or '')[:160]}")

    lines.append(f"\n📊 {pulse}")
    return "\n".join(lines)
