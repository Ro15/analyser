"""Fetch the current S&P 500 constituent list.

Primary: scrape Wikipedia. Fallback: a small static list of large-caps so the
pipeline still runs offline / when Wikipedia changes layout.

NOTE: this is CURRENT membership, not point-in-time -> backtest survivorship bias
(see CLAUDE.md "Known Data Caveat").
"""
import io

import pandas as pd
import requests

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_UA = {"User-Agent": "Mozilla/5.0 (catalyst-swing-bot; research)"}

# Fallback large-cap subset (not the full 500). Used only if the scrape fails.
STATIC_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY", "AVGO",
    "JPM", "TSLA", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "MRK",
    "ABBV", "CVX", "CRM", "AMD", "PEP", "KO", "ADBE", "WMT", "NFLX", "BAC",
    "MU", "QCOM", "TXN", "AMAT", "INTC", "ORCL", "CSCO", "TSM", "ARM", "PFE",
]


def get_sp500_tickers():
    """Return a list of S&P 500 tickers (yfinance-friendly: '.' -> '-')."""
    try:
        resp = requests.get(WIKI_URL, headers=_UA, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        tickers = df["Symbol"].astype(str).str.strip().tolist()
        tickers = [t.replace(".", "-") for t in tickers if t and t != "nan"]
        if len(tickers) >= 400:  # sanity check the scrape worked
            return tickers
    except Exception as e:  # noqa: BLE001 -- fall back on any scrape failure
        print(f"[sp500] Wikipedia scrape failed ({e}); using static fallback.")
    return list(STATIC_FALLBACK)


if __name__ == "__main__":
    t = get_sp500_tickers()
    print(f"{len(t)} tickers; first 10: {t[:10]}")
