"""Alpaca-backed stock sourcing: the broad US-equity universe + price bars.

PRIMARY source for sourcing; yfinance is the per-ticker fallback (see prices.py).

Two responsibilities:
  1. UNIVERSE -- list tradable US common stocks (NYSE/NASDAQ/AMEX, ETFs removed)
     and select the top-N most liquid via avg dollar volume. Ranking volume comes
     from Alpaca's free IEX feed, which UNDERSTATES true volume but is monotonic
     enough to pick the liquid names; gate 1 re-checks liquidity with full data.
  2. BARS -- bulk daily OHLCV for many symbols in few requests (far faster and
     more reliable than yfinance one-at-a-time at thousands-of-names scale).

Keys come from .env (ALPACA_API_KEY / ALPACA_SECRET); no keys -> functions raise
AlpacaUnavailable so callers can fall back to yfinance / the S&P 500 scrape.
"""
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

PAPER_BASE = "https://paper-api.alpaca.markets"   # assets list (account-scoped)
DATA_BASE = "https://data.alpaca.markets"          # market data (bars)

# ARCA/BATS listings are overwhelmingly ETFs; OTC is low quality. Keep the
# primary listing venues for operating companies.
_KEEP_EXCHANGES = {"NYSE", "NASDAQ", "AMEX"}
# Name hints that mark a fund/ETF rather than an operating company.
_FUND_HINTS = (
    "ETF", " FUND", "ISHARES", "SPDR", "PROSHARES", "INVESCO", "VANGUARD",
    "ETN", " TRUST", "INDEX FUND", "PORTFOLIO", "WISDOMTREE", "DIREXION",
    "X-TRACKERS", "GLOBAL X", "ETRACS",
)
# Dotted suffixes that mark a NON-common security (preferred, warrant, unit,
# rights, when-issued). Dual-class commons (.A/.B) are KEPT and mapped to '-'.
_NONCOMMON_SUFFIXES = (".PR", ".WS", ".WT", ".WI", ".U", ".UN", ".RT", ".CV")


class AlpacaUnavailable(Exception):
    """Raised when Alpaca keys are missing so callers can fall back."""


def is_configured():
    return bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET"))


def _headers():
    if not is_configured():
        raise AlpacaUnavailable("ALPACA_API_KEY / ALPACA_SECRET not set.")
    return {"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
            "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET")}


def is_common_stock(asset):
    """True if an Alpaca asset looks like a tradable US operating company."""
    if not asset.get("tradable"):
        return False
    if asset.get("exchange") not in _KEEP_EXCHANGES:
        return False
    symbol = asset.get("symbol") or ""
    if any(symbol.upper().endswith(sfx) or sfx + "." in symbol.upper()
           for sfx in _NONCOMMON_SUFFIXES):
        return False
    name = (asset.get("name") or "").upper()
    if any(hint in name for hint in _FUND_HINTS):
        return False
    return True


def list_equities():
    """All tradable US common stocks on the primary venues (ETFs excluded)."""
    r = requests.get(f"{PAPER_BASE}/v2/assets", headers=_headers(),
                     params={"status": "active", "asset_class": "us_equity"},
                     timeout=60)
    r.raise_for_status()
    symbols = {a["symbol"] for a in r.json() if is_common_stock(a)}
    return sorted(symbols)


def _bulk_daily_bars(symbols, start, feed="iex", chunk=200):
    """Daily bars for many symbols. Returns {symbol: [bar, ...]} (ascending).

    Chunks the symbol list (URL-length safety) and follows next_page_token.
    """
    out = {}
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        page_token = None
        while True:
            params = {"symbols": ",".join(batch), "timeframe": "1Day",
                      "start": start, "feed": feed, "limit": 10000}
            if page_token:
                params["page_token"] = page_token
            r = requests.get(f"{DATA_BASE}/v2/stocks/bars", headers=_headers(),
                             params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
            for sym, bars in (body.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bars)
            page_token = body.get("next_page_token")
            if not page_token:
                break
        time.sleep(0.3)  # be polite between chunks
    return out


def avg_dollar_volume(bars):
    """Mean close*volume over the supplied daily bars (0 if none)."""
    if not bars:
        return 0.0
    return sum(b["c"] * b["v"] for b in bars) / len(bars)


_PERIOD_DAYS = {"6mo": 183, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825}


def to_alpaca_symbol(symbol):
    """Universe tickers may use '/' or '-' for share classes; Alpaca uses '.'."""
    return symbol.replace("/", ".").replace("-", ".")


def _bars_to_df(bars):
    """Alpaca bar dicts -> normalized OHLCV frame with a naive daily index."""
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["t"], utc=True).dt.tz_localize(None).dt.normalize()
    df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                            "c": "close", "v": "volume"})
    return df.set_index("date")[["open", "high", "low", "close", "volume"]]


def fetch_many(tickers, period="3y", feed="sip"):
    """Bulk daily OHLCV for many tickers via Alpaca. SIP feed = full real volume.

    Returns {ticker: DataFrame}; tickers Alpaca has no data for are omitted.
    Far faster than per-ticker fetches at hundreds/thousands of names.
    """
    days = _PERIOD_DAYS.get(period, 1095)
    start = (pd.Timestamp.utcnow() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    alpaca_map = {to_alpaca_symbol(t): t for t in tickers}
    raw = _bulk_daily_bars(list(alpaca_map), start=start, feed=feed)
    out = {}
    for asym, bars in raw.items():
        df = _bars_to_df(bars)
        if not df.empty:
            out[alpaca_map.get(asym, asym)] = df
    return out


def fetch_ohlcv(ticker, period="3y", feed="sip"):
    """Alpaca daily OHLCV for one ticker; yfinance fallback on failure/no keys."""
    try:
        got = fetch_many([ticker], period=period, feed=feed)
        if ticker in got:
            return got[ticker]
    except (AlpacaUnavailable, requests.RequestException, KeyError):
        pass
    from data.ingest.prices import fetch_ohlcv as yf_fetch
    return yf_fetch(ticker, period=period)


if __name__ == "__main__":
    syms = list_equities()
    print(f"tradable US common stocks: {len(syms)}")
    sample = syms[:5]
    got = fetch_many(sample, period="1mo")
    for t in sample:
        df = got.get(t)
        n = len(df) if df is not None else 0
        last = f"${df['close'].iloc[-1]:.2f}" if n else "-"
        print(f"  {t:<6} {n} bars, last {last}")
