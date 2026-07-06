"""V2 debate stage (replaces gate 9's single veteran review).

Bull (DeepSeek) argues FOR reaching +target% in 90 days; Bear (DeepSeek)
argues AGAINST; the Judge (Claude, DeepSeek fallback) reads both plus the
lessons playbook and returns the structured verdict used for buys, sizing,
kill-conditions, and the journal.

Degradation: a missing bull/bear just narrows what the judge sees; NO judge
model at all -> verdict "unvetted", which can never become a buy (watchlist
only). All calls inherit llm_client's hard cost cap and LLM_MOCK mode.
"""
import json

from engine import llm_client
from engine.config import load_config

_BULL_SYS = (
    "You are the BULL analyst. Make the strongest honest case FOR this "
    "catalyst-anticipation long (90-day hold) using ONLY the evidence given. "
    "Respond ONLY with JSON: {\"case\":\"...\", \"strongest_points\":[...]}"
)
_BEAR_SYS = (
    "You are the BEAR analyst. Make the strongest honest case AGAINST this "
    "trade: what is already priced in, what kills it, why the market is right. "
    "Respond ONLY with JSON: {\"case\":\"...\", \"strongest_points\":[...]}"
)
_JUDGE_SYS_TMPL = (
    "You are the judge of a trading debate. Weigh the bull and bear cases and "
    "the past-lessons playbook, then decide. Target: +{target:.0%} within 90 "
    "days, exit on catalyst invalidation. Respond ONLY with JSON: "
    "{{\"verdict\":\"take|pass\", \"conviction\":1-10, \"p_target_90d\":0.0-1.0, "
    "\"size\":\"full|half\", \"kill_condition\":\"one concrete observable that "
    "invalidates the thesis\", \"reasoning\":\"...\"}}"
)


def _context(ticker, ctx):
    parts = [f"Ticker: {ticker}", f"Sector: {ctx.get('sector')}"]
    for key, label in [("gate_scores", "Gate scores"), ("catalyst", "Catalyst"),
                       ("setup", "Setup"), ("news_summary", "News"),
                       ("consensus", "Analyst consensus"),
                       ("short_interest", "Short interest"),
                       ("options", "Options snapshot")]:
        v = ctx.get(key)
        if v:
            parts.append(f"{label}: {json.dumps(v, default=str)}")
    return "\n".join(parts)


def _one_side(system, user):
    try:
        parsed = llm_client.extract_json(llm_client.call_deepseek(system, user))
        return (parsed or {}).get("case", "")
    except llm_client.LLMUnavailable:
        return ""


def run_debate(ticker, ctx):
    target = float(load_config()["backtest"]["target_pct"])
    user = _context(ticker, ctx)

    bull = _one_side(_BULL_SYS, user)
    bear = _one_side(_BEAR_SYS, user)

    judge_user = user
    if bull:
        judge_user += f"\n\nBULL CASE:\n{bull}"
    if bear:
        judge_user += f"\n\nBEAR CASE:\n{bear}"
    if ctx.get("playbook"):
        judge_user += f"\n\nLESSONS PLAYBOOK:\n{ctx['playbook']}"

    judge_sys = _JUDGE_SYS_TMPL.format(target=target)
    used = None
    try:
        raw = llm_client.call_claude(judge_sys, judge_user)
        used = "Claude"
    except llm_client.LLMUnavailable:
        try:
            raw = llm_client.call_deepseek(judge_sys, judge_user, max_tokens=700)
            used = "DeepSeek"
        except llm_client.LLMUnavailable:
            return {"verdict": "unvetted", "conviction": 0, "p_target_90d": None,
                    "size": None, "kill_condition": None, "bull_case": bull,
                    "bear_case": bear,
                    "reasoning": "No judge model available (no keys / cap reached).",
                    "used": None}

    parsed = llm_client.extract_json(raw) or {}
    verdict = str(parsed.get("verdict", "")).lower()
    if verdict not in ("take", "pass"):
        verdict = "unvetted"
    try:
        conviction = max(0, min(10, int(parsed.get("conviction") or 0)))
    except (TypeError, ValueError):
        conviction = 0
    p = parsed.get("p_target_90d")
    p = float(p) if isinstance(p, (int, float)) and 0.0 <= p <= 1.0 else None
    size = parsed.get("size") if parsed.get("size") in ("full", "half") else None
    if verdict == "take" and size is None:
        size = "full" if conviction >= 8 else "half"
    return {"verdict": verdict, "conviction": conviction, "p_target_90d": p,
            "size": size, "kill_condition": parsed.get("kill_condition"),
            "bull_case": bull, "bear_case": bear,
            "reasoning": parsed.get("reasoning", ""), "used": used}
