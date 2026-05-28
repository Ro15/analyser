"""Gate 8 -- news catalyst (DeepSeek).

Pulls ~14 days of news and asks DeepSeek whether a catalyst is COMING (not yet
priced in) vs already happened. Returns sentiment / catalyst_type / imminence /
red_flags. REJECT on strongly negative sentiment or fraud/SEC/major-customer-loss
red flags. Degrades to a neutral pass when the LLM/news are unavailable.
"""
from data.ingest import news
from engine import fundamentals, llm_client
from engine.config import load_config
from engine.types import GateResult

_SYSTEM = (
    "You are an equity catalyst analyst. Given recent news headlines about a "
    "company, decide whether a stock-moving catalyst is STILL COMING (not yet "
    "reflected in price) or has ALREADY happened/been priced in. Respond ONLY "
    "with JSON: {\"sentiment\":\"positive|neutral|negative\", "
    "\"catalyst_type\":\"...\", \"imminence\":\"coming|happened|none\", "
    "\"red_flags\":[\"fraud\"|\"sec_investigation\"|\"customer_loss\"|...], "
    "\"summary\":\"one sentence\"}."
)

_HARD_FLAGS = {"fraud", "sec_investigation", "accounting", "customer_loss",
               "bankruptcy", "delisting"}


def check(ticker, data):
    company = (data.get("info") or fundamentals.info(ticker)).get("shortName") or ticker
    days = load_config()["llm"]["news_lookback_days"]
    headlines = data.get("headlines")
    if headlines is None:
        headlines = news.recent_headlines(company, days=days)

    if not headlines:
        return GateResult(True, 5.0, "News: none found -> neutral pass (no signal).")

    digest = "\n".join(f"- {h['title']}" for h in headlines[:15] if h.get("title"))
    user = f"Company: {company} ({ticker})\nHeadlines (last {days}d):\n{digest}"

    try:
        raw = llm_client.call_deepseek(_SYSTEM, user)
    except llm_client.LLMUnavailable as e:
        return GateResult(True, 5.0, f"News LLM unavailable ({e}) -> neutral pass.")

    parsed = llm_client.extract_json(raw)
    if not parsed:
        return GateResult(True, 5.0, "News: unparseable LLM response -> neutral pass.")

    sentiment = parsed.get("sentiment", "neutral")
    imminence = parsed.get("imminence", "none")
    flags = {str(f).lower() for f in parsed.get("red_flags", [])}
    hard = flags & _HARD_FLAGS

    if hard:
        return GateResult(False, 0.0, f"News REJECT: red flags {sorted(hard)}.")
    if sentiment == "negative":
        return GateResult(False, 1.0, f"News REJECT: negative sentiment. {parsed.get('summary','')}")

    # Score favors a catalyst still COMING with positive sentiment.
    score = 5.0
    if imminence == "coming":
        score += 3.0
    elif imminence == "happened":
        score -= 2.0
    if sentiment == "positive":
        score += 1.0
    score = round(max(0.0, min(10.0, score)), 2)
    return GateResult(True, score,
                      f"News: {sentiment}, catalyst {parsed.get('catalyst_type','?')} "
                      f"({imminence}). {parsed.get('summary','')}")
