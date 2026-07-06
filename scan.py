"""Nightly entry point V2: funnel -> enrichment -> debate -> buys ->
position review -> post-mortems -> ONE digest message every market night.

Pipeline:
  1. hybrid voting funnel (guardrails block, voters score)  [engine.funnel.run]
  2. finalist enrichment (OpenBB shorts/options/insiders)   [engine.enrichment]
  3. finalist gate re-score (5.3, 6.5, 6.7, 6.8)            [funnel.run_finalist_gates]
  4. LLM stage: news (8), sentiment (8.5), bull/bear/judge debate, propagation (8.3)
  5. correlation / concentration filter (gate 9.5)
  6. structuring (gate 10) -> entry / +target% / invalidation / time-stop / size
  7. journal each buy (pipeline_version 2)
  8. resolutions -> position review (thesis_broken) -> post-mortems -> tuner
  9. ONE Telegram digest (buys + watchlist + exits + pulse) + full plan per buy

Usage:
  LLM_MOCK=1 python scan.py            # canned LLM responses, dry-run
  python scan.py --universe 200        # smaller slice for testing
  python scan.py --shadow              # live data; NO journal writes, NO Telegram
  python scan.py --live                # real run (used by the launchd schedule)

Scheduling: bash scripts/install_schedule.sh (launchd, weeknights 22:00).
"""
import argparse
import datetime as dt

from alerts import digest, formatter, telegram_bot
from backtest import data_cache
from catalyst import relationship_map
from engine import enrichment, funnel, structuring, thesis
from engine.config import load_config
from gates import g9_5_correlation
from journal import position_review, postmortem, tracker, tuner

PIPELINE_VERSION = 2


def _finalist_pipeline(universe, cfg, verbose):
    """Funnel -> enrichment -> finalist gates -> LLM/debate.
    Returns (finalist dicts, surviving funnel rows by ticker)."""
    top_n = cfg["llm"]["max_finalists"]
    result = funnel.run(universe=universe, top_n=top_n, verbose=verbose)
    if not result["regime"].passed:
        print(f"[scan] Regime no-go: {result['regime'].reasoning}. No buys tonight.")
        return [], {}
    survivors = result["survivors"]
    if not survivors:
        print("[scan] No survivors tonight.")
        return [], {}
    enrichment.enrich_finalists(survivors, top_n)
    kept, _ = funnel.run_finalist_gates(survivors, verbose=verbose)
    if not kept:
        return [], {}
    llm = funnel.run_llm_stage(kept, verbose=verbose)
    return llm["finalists"], {s["ticker"]: s for s in kept}


def run_scan(universe=None, dry_run=None, shadow=False, verbose=True):
    cfg = load_config()
    max_alerts = cfg.get("funnel", {}).get("max_alerts", 2)
    if universe is None:
        from data.ingest import universe as universe_src
        universe = universe_src.get_universe()

    finalists, by_ticker = _finalist_pipeline(universe, cfg, verbose)

    # Safety: only debate-approved names can become buys; never resurrect.
    approved = [f for f in finalists if f["llm_passed"]]
    candidates = [by_ticker[f["ticker"]] for f in approved
                  if f["ticker"] in by_ticker]
    kept_c, dropped_c = g9_5_correlation.filter_candidates(candidates)
    if verbose and dropped_c:
        print("\n[scan] correlation/sector filter dropped:")
        for d in dropped_c:
            print(f"    {d['ticker']}: {d['drop_reason']}")

    f_by_ticker = {f["ticker"]: f for f in finalists}
    buys, buy_msgs = [], []
    for s in kept_c[:max_alerts]:
        t = s["ticker"]
        deb = f_by_ticker[t]["debate"]
        plan = structuring.build_plan(
            t, s.get("_data", {}), catalyst=s.get("catalyst"),
            conviction=deb["conviction"], probability=deb["p_target_90d"],
            size=deb["size"])
        if plan is None:
            continue
        if not shadow:
            tracker.log_alert(
                plan, setup=s.get("reasonings", {}).get("g5_setups"),
                sector=s.get("sector"), regime="risk_on", scores=s.get("scores"),
                conviction=deb["conviction"], probability=deb["p_target_90d"],
                pipeline_version=PIPELINE_VERSION, size=deb["size"],
                kill_condition=deb["kill_condition"],
                debate={k: deb[k] for k in
                        ("verdict", "conviction", "p_target_90d", "size",
                         "bull_case", "bear_case", "reasoning")})
        buys.append(f_by_ticker[t])
        news_r = f_by_ticker[t]["news"].reasoning
        thesis_text = thesis.generate(
            t, sector=s.get("sector"), vote=s.get("vote"),
            catalyst=s.get("catalyst"),
            setup_reasoning=s.get("reasonings", {}).get("g5_setups"),
            news_summary=news_r, veteran_summary=deb["reasoning"])
        buy_msgs.append(formatter.format_alert(
            plan, news=news_r, veteran=deb["reasoning"],
            read_through=relationship_map.read_through(t)[:4] or None,
            reasonings=s.get("reasonings"), vote=s.get("vote"),
            sector=s.get("sector"), thesis=thesis_text))

    taken = {b["ticker"] for b in buys}
    watchlist = sorted((f for f in finalists if f["ticker"] not in taken),
                       key=lambda f: f["debate"]["conviction"], reverse=True)

    # Housekeeping BEFORE the digest so exits and the pulse reflect tonight.
    # Shadow runs skip anything that writes state.
    exits = []
    if not shadow:
        _resolve_open_positions(verbose=verbose)
        try:
            exits = position_review.review_open_positions(verbose=verbose)["exits"]
        except Exception as e:      # the review must never kill the digest
            print(f"[scan] position review failed: {e}")
        try:
            postmortem.run(verbose=verbose)
        except Exception as e:
            print(f"[scan] postmortem failed: {e}")
        result = tuner.tune()
        if verbose:
            print(f"[scan] tuner: {result.get('status')}")

    msg = digest.build_digest(buys, watchlist, exits, digest.portfolio_pulse(),
                              shadow=shadow)
    send_dry = bool(dry_run) or shadow
    is_live = (not send_dry) and telegram_bot.is_configured()
    print(f"\n[scan] digest + {len(buy_msgs)} buy alert(s) "
          f"({'LIVE' if is_live else 'DRY-RUN'}):\n")
    telegram_bot.send_alerts([msg] + buy_msgs, dry_run=send_dry)
    return {"digest": msg, "buys": buy_msgs, "exits": exits}


def _resolve_open_positions(verbose=True):
    """Auto-resolve open journal entries against today's last close."""
    if not tracker.open_alerts():
        return

    def _price_now(ticker):
        df = data_cache.get(ticker, period="3y")
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])

    tracker.mark_resolutions(_price_now)
    closed = [r for r in tracker.all_alerts() if r["status"] == "closed"]
    if verbose:
        print(f"[scan] journal: {len(closed)} closed, "
              f"{len(tracker.open_alerts())} open")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", type=int, default=None,
                    help="number of names to scan (default: full universe)")
    ap.add_argument("--live", action="store_true",
                    help="actually send Telegram (used by the schedule)")
    ap.add_argument("--shadow", action="store_true",
                    help="live data; NO journal writes, NO Telegram")
    args = ap.parse_args()
    from data.ingest import universe as universe_src
    uni = universe_src.get_universe()[: args.universe] if args.universe else None
    print(f"[scan] {dt.datetime.now():%Y-%m-%d %H:%M} starting nightly scan (V2)")
    run_scan(universe=uni, dry_run=not args.live, shadow=args.shadow)
