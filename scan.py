"""Nightly entry point: run the full hybrid funnel end-to-end and fire alerts.

Pipeline:
  1. hybrid voting funnel (guardrails block, voters score)  [engine.funnel.run]
  2. LLM stage (8 news / DeepSeek, 9 veteran, 8.5 sentiment, 8.3 propagation)
  3. correlation / concentration filter (gate 9.5)
  4. structuring (gate 10) -> entry/target/invalidation/time-stop
  5. journal each alert
  6. send up to `funnel.max_alerts` Telegram messages (DRY-RUN unless TELEGRAM_* set)

Usage:
  python scan.py                 # full universe, dry-run telegram
  LLM_MOCK=1 python scan.py      # canned LLM responses (no key/network)
  python scan.py --universe 200  # smaller slice for testing
  python scan.py --live          # actually push to Telegram (used by the schedule)

Scheduling: install the launchd agent that runs this every weeknight at 22:00:
  bash scripts/install_schedule.sh
"""
import argparse
import datetime as dt

from alerts import formatter, telegram_bot
from backtest import data_cache
from catalyst import relationship_map
from data.ingest import universe as universe_src
from engine import funnel, structuring, thesis
from engine.config import load_config
from gates import g9_5_correlation
from journal import tracker, tuner

def run_scan(universe=None, dry_run=None, verbose=True):
    cfg = load_config()
    max_alerts = cfg.get("funnel", {}).get("max_alerts", 2)
    if universe is None:
        universe = universe_src.get_universe()

    result = funnel.run(universe=universe, top_n=cfg["llm"]["max_finalists"],
                        verbose=verbose)
    regime = result["regime"]
    if not regime.passed:
        print(f"[scan] Regime no-go: {regime.reasoning}. No alerts tonight.")
        return []

    survivors = result["survivors"]
    if not survivors:
        print("[scan] No survivors tonight.")
        return []

    # LLM stage (gates 8, 8.5, 9, 8.3).
    llm = funnel.run_llm_stage(survivors, verbose=verbose)
    approved_tickers = {r["ticker"] for r in llm["finalists"] if r["llm_passed"]}
    llm_by_ticker = {r["ticker"]: r for r in llm["finalists"]}

    # Safety: if the LLM rejected everything (e.g. fraud flag night, negative
    # news everywhere), send NO alerts. Never resurrect a hard-flagged name.
    candidates = [s for s in survivors if s["ticker"] in approved_tickers]
    if not candidates:
        print("[scan] LLM rejected all finalists -> no alerts tonight.")
        return []

    # Correlation / concentration filter (gate 9.5).
    kept, dropped = g9_5_correlation.filter_candidates(candidates)
    if verbose and dropped:
        print("\n[scan] correlation/sector filter dropped:")
        for d in dropped:
            print(f"    {d['ticker']}: {d['drop_reason']}")

    alerts = kept[:max_alerts]
    messages = []
    for s in alerts:
        t = s["ticker"]
        lr = llm_by_ticker.get(t, {})
        vet = lr.get("veteran")
        plan = structuring.build_plan(t, s.get("_data", {}), catalyst=s.get("catalyst"))
        if plan is None:
            continue
        tracker.log_alert(
            plan,
            setup=s.get("reasonings", {}).get("g5_setups"),
            sector=s.get("sector"),
            regime="risk_on",
            scores=s.get("scores"),
        )
        thesis_text = thesis.generate(
            t,
            sector=s.get("sector"),
            vote=s.get("vote"),
            catalyst=s.get("catalyst"),
            setup_reasoning=s.get("reasonings", {}).get("g5_setups"),
            news_summary=(lr.get("news").reasoning if lr.get("news") else None),
            veteran_summary=(vet.reasoning if vet else None),
        )
        msg = formatter.format_alert(
            plan,
            news=(lr.get("news").reasoning if lr.get("news") else None),
            veteran=(vet.reasoning if vet else None),
            read_through=relationship_map.read_through(t)[:4] or None,
            reasonings=s.get("reasonings"),
            vote=s.get("vote"),
            sector=s.get("sector"),
            thesis=thesis_text,
        )
        messages.append(msg)

    is_live = (not dry_run) and telegram_bot.is_configured()
    print(f"\n[scan] firing {len(messages)} alert(s) "
          f"({'LIVE' if is_live else 'DRY-RUN'}):\n")
    telegram_bot.send_alerts(messages, dry_run=dry_run)
    return messages


def nightly_housekeeping(verbose=True):
    """Run every night regardless of alert count: mark stale positions
    resolved, and ask the tuner to nudge per-gate weights. The tuner is a
    no-op until enough trades have closed (>=20 by default)."""
    _resolve_open_positions(verbose=verbose)
    result = tuner.tune()
    if verbose:
        print(f"[scan] tuner: {result.get('status')}")


def _resolve_open_positions(verbose=True):
    """Auto-resolve any open journal entries against today's last close."""
    open_ = tracker.open_alerts()
    if not open_:
        return

    def _price_now(ticker):
        df = data_cache.get(ticker, period="3y")
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])

    tracker.mark_resolutions(_price_now)
    closed = [r for r in tracker.all_alerts() if r["status"] == "closed"]
    if verbose:
        still_open = tracker.open_alerts()
        print(f"[scan] journal: {len(closed)} closed, {len(still_open)} open")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", type=int, default=None,
                    help="number of S&P names to scan (default: config universe_size)")
    ap.add_argument("--live", action="store_true",
                    help="actually send Telegram (default dry-run)")
    args = ap.parse_args()
    uni = universe_src.get_universe()[: args.universe] if args.universe else None
    print(f"[scan] {dt.datetime.now():%Y-%m-%d %H:%M} starting nightly scan")
    try:
        run_scan(universe=uni, dry_run=not args.live)
    finally:
        # Always run housekeeping (resolutions + tuner) even on no-alert nights.
        nightly_housekeeping(verbose=True)
