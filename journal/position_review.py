"""V2 nightly open-position review: the open-position doctor.

Cheap deterministic red flags first (no LLM, every open position); the judge
is consulted ONLY for positions with >= position_review.min_flags flags, and
ONLY the judge may declare a thesis dead (-> resolution "thesis_broken").

GUARDRAILS: price weakness alone can never close a position (it is one flag
among several), and no judge model available -> flag, never auto-close.
"""
import datetime as dt
import json

from backtest import data_cache
from data.ingest import openbb_source
from engine import llm_client
from engine.config import load_config
from engine.indicators import sma
from journal import tracker

_SYS = (
    "Position review: you are the judge who approved this swing trade. Given "
    "the entry thesis and tonight's red flags, decide if the thesis is dead "
    "(exit now) or still valid (hold). Respond ONLY with JSON: "
    "{\"thesis_dead\":true|false, \"reasoning\":\"...\"}"
)


def _red_flags(rec, bars, short_vol, today, cfg):
    flags = []
    grace = int(cfg.get("catalyst_grace_days", 5))
    brk = float(cfg.get("trend_break_pct", 0.03))
    spike = float(cfg.get("short_spike_ratio", 1.5))

    price = float(bars["close"].iloc[-1])

    cat_date = (rec.get("catalyst") or {}).get("date")
    if cat_date:
        try:
            passed_days = (today - dt.date.fromisoformat(str(cat_date)[:10])).days
            if passed_days > grace and price < rec["target"]:
                flags.append(f"catalyst passed {passed_days}d ago without "
                             "reaching target")
        except ValueError:
            pass

    if len(bars) >= 50:
        ma50 = float(sma(bars["close"], 50).iloc[-1])
        if ma50 == ma50 and price < ma50 * (1 - brk):
            flags.append(f"trend break: close {price:.2f} < 50DMA {ma50:.2f} "
                         f"by >{brk:.0%}")

    pcts = (short_vol or {}).get("short_pct") or []
    if len(pcts) >= 6:
        mid = sorted(pcts)[len(pcts) // 2]
        if mid > 0 and pcts[-1] / mid >= spike:
            flags.append(f"short-volume spike: {pcts[-1]:.0%} vs median {mid:.0%}")

    return flags


def review_open_positions(verbose=True, today=None):
    cfg = load_config().get("position_review", {})
    min_flags = int(cfg.get("min_flags", 2))
    today = today or dt.date.today()
    exits, flagged = [], []

    for rec in tracker.open_alerts():
        t = rec["ticker"]
        bars = data_cache.get(t, period="1y")
        if bars is None or bars.empty:
            continue
        flags = _red_flags(rec, bars, openbb_source.short_volume(t), today, cfg)
        if len(flags) < min_flags:
            continue
        flagged.append({"ticker": t, "flags": flags})

        price = float(bars["close"].iloc[-1])
        ret = price / rec["reference_price"] - 1
        user = json.dumps(
            {"ticker": t,
             "entry_thesis": {"setup": rec.get("setup"),
                              "catalyst": rec.get("catalyst"),
                              "kill_condition": rec.get("kill_condition"),
                              "debate_reasoning": (rec.get("debate") or {}).get("reasoning")},
             "red_flags": flags,
             "current_return": round(ret, 4)},
            default=str)
        try:
            raw = llm_client.call_claude(_SYS, user, max_tokens=400)
        except llm_client.LLMUnavailable:
            try:
                raw = llm_client.call_deepseek(_SYS, user, max_tokens=400)
            except llm_client.LLMUnavailable:
                continue  # GUARDRAIL: never auto-close unvetted
        parsed = llm_client.extract_json(raw) or {}
        if parsed.get("thesis_dead") is True:
            tracker.resolve(rec["id"], resolution="thesis_broken",
                            realized_return=ret, catalyst_happened=False,
                            on=today)
            exits.append({"ticker": t, "return": ret,
                          "reason": parsed.get("reasoning", ""), "flags": flags})

    if verbose and (exits or flagged):
        print(f"[review] {len(flagged)} flagged, {len(exits)} thesis-broken exits")
    return {"exits": exits, "flagged": flagged}
