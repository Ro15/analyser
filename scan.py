"""Nightly entry point: run the full funnel end-to-end and fire alerts.

Pipeline:
  1. deterministic funnel (gates 0..7.5) + catalyst boost   [engine.funnel.run]
  2. LLM stage (8 news, 8.5 sentiment, 9 veteran, 8.3 propagation)
  3. correlation / concentration filter (gate 9.5)
  4. structuring (gate 10) -> entry/target/invalidation/time-stop
  5. journal each alert (gate 12)
  6. send 3-4 Telegram alerts (DRY-RUN unless TELEGRAM_* configured)

Usage:
  python scan.py                 # paper/dry-run, default universe slice
  LLM_MOCK=1 python scan.py      # exercise LLM stage with canned responses
  python scan.py --universe 200  # larger universe slice

Scheduling: run nightly via cron, e.g. ~2 AM ET (after US close, before open):
  0 2 * * 1-5  cd /path/to/analyser && /usr/bin/python3 scan.py >> scan.log 2>&1
"""
import argparse
import datetime as dt

from alerts import formatter, telegram_bot
from catalyst import relationship_map
from data.ingest.sp500 import get_sp500_tickers
from engine import funnel, structuring
from engine.config import load_config
from gates import g9_5_correlation
from journal import tracker

MAX_ALERTS = 4


def run_scan(universe=None, dry_run=None, verbose=True):
    cfg = load_config()
    if universe is None:
        universe = get_sp500_tickers()[: cfg["backtest"]["universe_size"]]

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

    candidates = [s for s in survivors if s["ticker"] in approved_tickers] or survivors

    # Correlation / concentration filter (gate 9.5).
    kept, dropped = g9_5_correlation.filter_candidates(candidates)
    if verbose and dropped:
        print("\n[scan] correlation/sector filter dropped:")
        for d in dropped:
            print(f"    {d['ticker']}: {d['drop_reason']}")

    alerts = kept[:MAX_ALERTS]
    messages = []
    for s in alerts:
        t = s["ticker"]
        lr = llm_by_ticker.get(t, {})
        vet = lr.get("veteran")
        conviction = None
        if vet and "conviction" in (vet.reasoning or ""):
            conviction = None  # parsed conviction lives in the LLM result if needed
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
        msg = formatter.format_alert(
            plan,
            news=(lr.get("news").reasoning if lr.get("news") else None),
            veteran=(vet.reasoning if vet else None),
            read_through=relationship_map.read_through(t)[:4] or None,
        )
        messages.append(msg)

    print(f"\n[scan] firing {len(messages)} alert(s) "
          f"({'DRY-RUN' if not telegram_bot.is_configured() else 'LIVE'}):\n")
    telegram_bot.send_alerts(messages, dry_run=dry_run)
    return messages


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", type=int, default=None,
                    help="number of S&P names to scan (default: config universe_size)")
    ap.add_argument("--live", action="store_true",
                    help="actually send Telegram (default dry-run)")
    args = ap.parse_args()
    uni = get_sp500_tickers()[: args.universe] if args.universe else None
    print(f"[scan] {dt.datetime.now():%Y-%m-%d %H:%M} starting nightly scan")
    run_scan(universe=uni, dry_run=not args.live)
