"""Gate 9 -- veteran review (Claude -> DeepSeek fallback).

Full-context review of a finalist: red-team the thesis, cite 3-5 historical
analog setups, and output a calibrated probability of +15% within 90 days plus
conviction 1-5. REJECT if the verdict is "would not take" OR conviction < 3.

Tries Claude first (the original reviewer). When Claude is unavailable (no key,
cap reached), falls back to DeepSeek with the same prompt -- cheap and capable
enough for this judgement, and far better than skipping the review entirely.
Only if BOTH are unavailable does the gate pass with an UN-VETTED warning.
"""
import json

from engine import llm_client
from engine.types import GateResult

_SYSTEM = (
    "You are a veteran swing trader reviewing a catalyst-anticipation long idea "
    "(60-90 day hold, +15% target, exit on catalyst invalidation). Red-team the "
    "thesis, cite 3-5 historical analog setups and how they resolved, and give a "
    "calibrated probability of +15% within 90 days. Respond ONLY with JSON: "
    "{\"verdict\":\"would take|would not take\", \"conviction\":1-5, "
    "\"probability_15pct_90d\":0.0-1.0, \"thesis_risks\":[...], "
    "\"analogs\":[...], \"summary\":\"...\"}."
)


def _context(ticker, data):
    scores = data.get("gate_scores", {})
    cat = data.get("catalyst")
    parts = [f"Ticker: {ticker}", f"Sector: {data.get('sector')}"]
    if scores:
        parts.append("Gate scores: " + json.dumps(scores))
    if cat:
        parts.append(f"Catalyst: {cat.get('type')} in {cat.get('days_out')}d "
                     f"-- {cat.get('description')}")
    if data.get("setup"):
        parts.append(f"Setup: {data['setup']}")
    if data.get("news_summary"):
        parts.append(f"News: {data['news_summary']}")
    return "\n".join(parts)


def check(ticker, data):
    user = _context(ticker, data)
    used = None
    try:
        raw = llm_client.call_claude(_SYSTEM, user)
        used = "Claude"
    except llm_client.LLMUnavailable:
        try:
            raw = llm_client.call_deepseek(_SYSTEM, user, max_tokens=700)
            used = "DeepSeek"
        except llm_client.LLMUnavailable as e:
            return GateResult(True, 5.0,
                              f"Veteran review SKIPPED ({e}) -> UN-VETTED, treat with caution.")

    parsed = llm_client.extract_json(raw)
    if not parsed:
        return GateResult(True, 5.0, f"Veteran review (via {used}) unparseable -> UN-VETTED.")

    verdict = str(parsed.get("verdict", "")).lower()
    conviction = parsed.get("conviction", 0) or 0
    prob = parsed.get("probability_15pct_90d")
    summary = parsed.get("summary", "")

    if "not take" in verdict or conviction < 3:
        return GateResult(False, float(conviction),
                          f"Veteran REJECT via {used} (verdict='{verdict}', "
                          f"conviction={conviction}). {summary}")

    score = round(min(10.0, conviction * 2.0), 2)
    prob_txt = f", p(+15%/90d)={prob:.0%}" if isinstance(prob, (int, float)) else ""
    return GateResult(True, score,
                      f"Veteran APPROVE via {used} (conviction {conviction}/5{prob_txt}). {summary}")
