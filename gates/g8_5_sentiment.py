"""Gate 8.5 -- contrarian sentiment guard (LOW-WEIGHT, NOISY).

Reduces conviction when the stock looks like a hype trade (protects against
buying tops). Two complementary signals:
  1) PRICE/VOLUME euphoria proxy (always runs): parabolic 1mo runup, blow-off
     volume, stretched above 50DMA.
  2) NEWS-DRIVEN hype check (when DeepSeek + headlines are available): asks
     the LLM whether recent headlines read as FOMO / meme-stock / "everyone's
     piling in" vs measured / analytical.

The two are blended (LLM nudges the keyword signal up or down). Never hard-
rejects; this is a soft signal in the vote.
"""
from engine import llm_client
from engine.indicators import sma
from engine.types import GateResult

_SENTIMENT_SYSTEM = (
    "You judge whether recent stock-news headlines sound like RETAIL HYPE / "
    "FOMO / meme-fever (e.g. 'to the moon', breathless price-target hikes, "
    "social-media buzz, parabolic chatter) vs MEASURED, ANALYTICAL coverage. "
    "Respond ONLY with JSON: {\"hype\": true|false, \"confidence\": 0.0-1.0, "
    "\"why\": \"one short phrase\"}."
)


def _llm_hype_signal(ticker, headlines):
    """Returns (hype_bool, confidence_0_1, why_str) or None if unavailable."""
    if not headlines:
        return None
    digest = "\n".join(f"- {h.get('title', '')}" for h in headlines[:12]
                       if h.get("title"))
    if not digest:
        return None
    try:
        raw = llm_client.call_deepseek(
            _SENTIMENT_SYSTEM, f"Ticker: {ticker}\nHeadlines:\n{digest}",
            max_tokens=120)
    except llm_client.LLMUnavailable:
        return None
    parsed = llm_client.extract_json(raw)
    if not parsed:
        return None
    return (bool(parsed.get("hype")),
            float(parsed.get("confidence") or 0.5),
            str(parsed.get("why") or ""))


def check(ticker, data):
    bars = data.get("bars")
    if bars is None or len(bars) < 60:
        return GateResult(True, 5.0, "Sentiment: insufficient data -> neutral (noisy).")

    c = bars["close"]
    runup_1m = float(c.iloc[-1] / c.iloc[-21] - 1)
    ma50 = sma(c, 50).iloc[-1]
    stretch = float(c.iloc[-1] / ma50 - 1) if ma50 == ma50 else 0.0
    vol_recent = float(bars["volume"].iloc[-5:].mean())
    vol_base = float(bars["volume"].iloc[-60:-5].mean())
    vol_spike = vol_recent / vol_base if vol_base > 0 else 1.0

    euphoria = 0
    notes = []
    if runup_1m > 0.20:
        euphoria += 1; notes.append(f"+{runup_1m*100:.0f}% 1mo")
    if stretch > 0.15:
        euphoria += 1; notes.append(f"{stretch*100:.0f}% above 50DMA")
    if vol_spike > 2.0:
        euphoria += 1; notes.append(f"{vol_spike:.1f}x volume blow-off")

    # Base score: 5 neutral, -1.5 per euphoria signal, floored at 2.0.
    score = max(2.0, 5.0 - euphoria * 1.5)
    detail = "; ".join(notes) if notes else "no euphoria signals"

    # LLM nudge: if DeepSeek + headlines say it's hype, push score down further;
    # if it explicitly says NOT hype, give a small boost back toward neutral.
    llm = _llm_hype_signal(ticker, data.get("headlines"))
    if llm is not None:
        hype, conf, why = llm
        if hype:
            score = max(2.0, score - 2.0 * conf)
            detail += f"; AI: hype ({conf:.0%}) -- {why}"
        else:
            score = min(10.0, score + 0.5 * conf)
            detail += f"; AI: not hype ({conf:.0%}) -- {why}"

    return GateResult(True, round(score, 2),
                      f"[noisy/low-weight] Contrarian: euphoria {euphoria}/3 ({detail}).")
