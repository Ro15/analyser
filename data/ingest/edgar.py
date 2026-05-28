"""Minimal SEC EDGAR client for insider (Form 4) activity.

Uses the public data.sec.gov JSON APIs. SEC requires a descriptive User-Agent.
All calls are best-effort: on any failure they return None so gates degrade to
neutral. No API key needed (EDGAR is free/public).

NOTE: 13F institutional holdings carry a ~45-day reporting lag; this module
focuses on Form 4 (insider transactions), which is timelier.
"""
import functools
import os

import requests

_UA = os.getenv("SEC_USER_AGENT", "catalyst-swing-bot research ravi.rohit15@gmail.com")
_HEADERS = {"User-Agent": _UA, "Accept-Encoding": "gzip, deflate"}
_TIMEOUT = 10


@functools.lru_cache(maxsize=1)
def _ticker_cik_map():
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return {row["ticker"].upper(): str(row["cik_str"]).zfill(10)
                for row in data.values()}
    except Exception:
        return {}


def cik_for(ticker):
    return _ticker_cik_map().get(ticker.upper())


@functools.lru_cache(maxsize=256)
def recent_filings(ticker):
    """Return the issuer's recent-filings dict, or None."""
    cik = cik_for(ticker)
    if not cik:
        return None
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                         headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json().get("filings", {}).get("recent", {})
    except Exception:
        return None


def form4_count(ticker, days=90):
    """Count Form 4 filings in the last `days`. None if unavailable.

    Form 4 covers insider transactions; a burst is a rough cluster-buying proxy
    (direction isn't parsed here -- the LLM/structuring layer can refine later).
    """
    import datetime as dt

    recent = recent_filings(ticker)
    if not recent:
        return None
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    cutoff = dt.date.today() - dt.timedelta(days=days)
    count = 0
    for form, d in zip(forms, dates):
        if form == "4":
            try:
                if dt.date.fromisoformat(d) >= cutoff:
                    count += 1
            except ValueError:
                continue
    return count
