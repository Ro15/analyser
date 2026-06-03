"""Multi-source free news gatherer (ported from the `cl` trading bot, expanded).

Pulls stock news from several keyless / already-keyed sources, dedupes by
headline, scores keyword sentiment, and aggregates a per-ticker bullish/bearish
read. No NewsAPI key needed.

Sources (all free; Alpaca reuses the keys already in .env):
  1. Alpaca news  (Benzinga-sourced, high quality)
  2. yfinance .news
  3. Yahoo Finance RSS
  4. Google News RSS (per-ticker search)
  5. Seeking Alpha RSS
  6. Bing News RSS (broad / international)
  7. Finviz (web scrape)
  8. Motley Fool RSS

Headlines are returned in the same shape as data.ingest.news (title /
description / source / publishedAt) so the news gate (gates/g8_news_catalyst)
consumes them via data["headlines"] with no change. Keyword sentiment is a cheap
pre-signal; the LLM (DeepSeek) still does the real catalyst judgement.

NOTE: feedparser.parse() has no network timeout and can hang, so every feed is
fetched via requests (hard timeout) and parsed from the returned bytes.
"""
import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()  # so _from_alpaca can read ALPACA_* keys when run standalone

_STATE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, ".state")
_OUT_PATH = os.path.join(_STATE_DIR, "news_scan.json")

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120"}

BULLISH = [
    "surge", "beat", "record", "rally", "upgrade", "buy", "strong", "growth",
    "profit", "breakout", "exceed", "positive", "gain", "rise", "soar", "jump",
    "boom", "bullish", "outperform", "recovery", "rebound", "highs", "upside",
    "raise", "raised", "boost", "boosts", "top", "tops", "acquire", "acquires",
]
BEARISH = [
    "miss", "missed", "downgrade", "sell", "loss", "crash", "decline", "lawsuit",
    "recall", "weak", "cut", "cuts", "layoff", "fraud", "warning", "fall", "falls",
    "plunge", "bearish", "underperform", "risk", "concern", "pressure", "fear",
    "tumble", "slump", "drops", "slides", "probe", "investigation", "halt",
]


def score(text):
    """Cheap keyword sentiment label for a headline/summary."""
    t = (text or "").lower()
    bull = sum(1 for w in BULLISH if w in t)
    bear = sum(1 for w in BEARISH if w in t)
    if bull == 0 and bear == 0:
        return "NEUTRAL"
    if bull > bear * 1.5:
        return "STRONG_BULLISH"
    if bear > bull * 1.5:
        return "STRONG_BEARISH"
    if bull > bear:
        return "BULLISH_BIAS"
    if bear > bull:
        return "BEARISH_BIAS"
    return "MIXED"


def _item(title, description, source, published):
    return {"title": title or "", "description": (description or "")[:300],
            "source": source, "publishedAt": str(published or "")}


def _fetch(url, timeout=12):
    """GET bytes with a hard timeout (feedparser.parse has no timeout of its own)."""
    try:
        r = requests.get(url, headers=_UA, timeout=timeout)
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None


def _rss(url, source, limit=10):
    feed = feedparser.parse(_fetch(url) or b"")
    return [_item(e.get("title"), e.get("summary"), source, e.get("published"))
            for e in feed.entries[:limit]]


def _from_alpaca(ticker):
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET")
    if not (key and secret):
        return []
    try:
        r = requests.get("https://data.alpaca.markets/v1beta1/news",
                         headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                         params={"symbols": ticker, "limit": 15}, timeout=15)
        if r.status_code != 200:
            return []
        return [_item(n.get("headline"), n.get("summary"), "alpaca",
                      n.get("created_at")) for n in r.json().get("news", [])]
    except requests.RequestException:
        return []


def _from_yfinance(ticker, timeout=8):
    """yf.Ticker(t).news has no timeout and can hang for minutes; bound it."""
    import threading
    out = []

    def _do():
        try:
            for it in (yf.Ticker(ticker).news or [])[:10]:
                c = it.get("content") or it
                title = c.get("title") or ""
                if title:
                    out.append(_item(title, c.get("summary"), "yfinance",
                                     c.get("pubDate") or c.get("providerPublishTime")))
        except Exception:
            pass

    th = threading.Thread(target=_do, daemon=True)
    th.start()
    th.join(timeout)
    return out  # whatever we got; abandoned if still running


def _from_yahoo_rss(ticker):
    return _rss(f"https://feeds.finance.yahoo.com/rss/2.0/headline"
                f"?s={ticker}&region=US&lang=en-US", "yahoo_rss")


def _from_google_rss(ticker):
    return _rss(f"https://news.google.com/rss/search"
                f"?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en", "google_rss")


def _from_seekingalpha(ticker):
    return _rss(f"https://seekingalpha.com/api/sa/combined/{ticker}.xml",
                "seekingalpha")


def _from_bing(ticker):
    return _rss(f"https://www.bing.com/news/search?q={ticker}+stock&format=rss",
                "bing")


def _from_finviz(ticker):
    try:
        r = requests.get(f"https://finviz.com/quote.ashx?t={ticker}",
                         headers=_UA, timeout=10)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for row in soup.select("table.fullview-news-outer tr")[:10]:
            a = row.find("a")
            if a and a.text.strip():
                out.append(_item(a.text.strip(), "", "finviz", ""))
        return out
    except Exception:
        return []


def _from_fool_rss(ticker):
    return _rss(f"https://www.fool.com/feeds/index.aspx"
                f"?id=fool-articles&symbols={ticker}", "fool_rss", limit=8)


_SOURCES = [_from_alpaca, _from_yfinance, _from_yahoo_rss, _from_google_rss,
            _from_seekingalpha, _from_bing, _from_finviz, _from_fool_rss]


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        key = (it.get("title", "")[:60] or "").lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def gather(ticker):
    """All deduped headlines for one ticker, each tagged with keyword sentiment.

    Sources are fetched concurrently so one slow site can't drag out the total.
    Returns a list of {title, description, source, publishedAt, sentiment}.
    """
    items = []
    with ThreadPoolExecutor(max_workers=len(_SOURCES)) as ex:
        futures = [ex.submit(fn, ticker) for fn in _SOURCES]
        for fut in as_completed(futures):
            try:
                items.extend(fut.result())
            except Exception:
                pass
    items = _dedupe(items)
    for it in items:
        it["sentiment"] = score(f"{it['title']} {it['description']}")
    return items


def aggregate(ticker):
    """Per-ticker rollup: count, an overall bullish/bearish read, top headlines."""
    items = gather(ticker)
    counts = {k: 0 for k in ("STRONG_BULLISH", "BULLISH_BIAS", "MIXED",
                             "NEUTRAL", "BEARISH_BIAS", "STRONG_BEARISH")}
    for it in items:
        counts[it["sentiment"]] = counts.get(it["sentiment"], 0) + 1
    bull = counts["STRONG_BULLISH"] * 2 + counts["BULLISH_BIAS"]
    bear = counts["STRONG_BEARISH"] * 2 + counts["BEARISH_BIAS"]
    if bull == 0 and bear == 0:
        agg = "NEUTRAL"
    elif bull > bear * 1.5:
        agg = "BULLISH"
    elif bear > bull * 1.5:
        agg = "BEARISH"
    else:
        agg = "MIXED"
    return {"ticker": ticker, "count": len(items), "aggregate": agg,
            "sentiment_counts": counts, "headlines": items[:8]}


def scan_universe(tickers=None, max_workers=8, write=True):
    """Batch-scan many tickers concurrently. Writes .state/news_scan.json."""
    import json
    if tickers is None:
        from data.ingest.universe import get_universe
        tickers = get_universe()
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(aggregate, t): t for t in tickers}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                results[t] = fut.result()
            except Exception:
                results[t] = {"ticker": t, "count": 0, "aggregate": "NEUTRAL",
                              "sentiment_counts": {}, "headlines": []}
    out = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
           "results": results}
    if write:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_OUT_PATH, "w") as f:
            json.dump(out, f, indent=2)
    return out


if __name__ == "__main__":
    import sys
    for tk in sys.argv[1:] or ["AAPL"]:
        a = aggregate(tk)
        print(f"{tk}: {a['count']} headlines, {a['aggregate']}")
        for h in a["headlines"][:5]:
            print(f"  [{h['sentiment']:<14}] ({h['source']}) {h['title'][:80]}")
