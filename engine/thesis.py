"""DeepSeek-written 2-3 sentence thesis for each alert.

Runs once per alert (after all gates pass and the structuring layer has built
the trade plan). Pulls everything we know about the name -- catalyst, setup,
news verdict, sector, vote -- and asks DeepSeek to write a tight, plain-English
explanation of WHY this stock right now. The output goes straight into the
Telegram message so the user gets a clear thesis on their phone.

Cheap: each call is ~$0.00005. No JSON, no schema -- just the thesis.
"""
from engine import llm_client

_SYSTEM = (
    "You are writing the THESIS line for a catalyst-anticipation swing alert. "
    "The strategy: buy a stock that's in a healthy uptrend AHEAD of a known "
    "catalyst (earnings, product launch, FDA, etc.) that is NOT YET priced in. "
    "Hold 60-90 days, target +15%, exit if the catalyst is cancelled or fades.\n\n"
    "Write 2-3 SHORT sentences in plain English explaining WHY this specific "
    "stock RIGHT NOW: the catalyst, why it isn't priced in, and the technical/"
    "fundamental edge. No bullet points, no JSON, no hedging fluff. Be concrete. "
    "If something is weak (e.g. catalyst already happened, or no clean setup), "
    "say so honestly in one of the sentences."
)


def generate(ticker, *, sector=None, vote=None, catalyst=None,
             setup_reasoning=None, news_summary=None, veteran_summary=None,
             extra=None):
    """Return a 2-3 sentence thesis string. None if DeepSeek is unavailable."""
    parts = [f"Ticker: {ticker}"]
    if sector:
        parts.append(f"Sector: {sector}")
    if vote is not None:
        parts.append(f"Internal vote score: {vote}/10")
    if catalyst:
        parts.append(
            f"Catalyst: {catalyst.get('type')} in {catalyst.get('days_out')}d "
            f"({catalyst.get('date')}) -- {catalyst.get('description', '')}"
        )
    if setup_reasoning:
        parts.append(f"Technical setup: {setup_reasoning}")
    if news_summary:
        parts.append(f"News (AI): {news_summary}")
    if veteran_summary:
        parts.append(f"Veteran review: {veteran_summary}")
    if extra:
        parts.append(extra)

    try:
        text = llm_client.call_deepseek(_SYSTEM, "\n".join(parts), json_mode=False,
                                        max_tokens=220)
    except llm_client.LLMUnavailable:
        return None
    return (text or "").strip()
