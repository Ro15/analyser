"""Assemble the `data` dict gates consume.

Loads a ticker's bars (from Postgres if present, else fresh from yfinance and
cached when a DB is available) plus market-level series (^VIX, ^GSPC) and
breadth for Gate 0.
"""
import pandas as pd

from data import store
from data.ingest.prices import fetch_ohlcv
from data.ingest.sp500 import get_sp500_tickers
from engine.indicators import sma


def load_ticker_bars(ticker, period="3y", prefer_db=True):
    """Return a bars DataFrame, pulling fresh from yfinance if DB has nothing."""
    if prefer_db and store.is_available():
        df = store.load_bars(ticker)
        if df is not None and not df.empty:
            return df
    df = fetch_ohlcv(ticker, period=period)
    if not df.empty and store.is_available():
        try:
            store.create_tables()
            store.upsert_bars(ticker, df)
        except Exception:
            pass  # caching is best-effort; never block analysis on DB
    return df


def load_market(period="2y"):
    """VIX + SPX frames for Gate 0."""
    return {"vix": fetch_ohlcv("^VIX", period=period),
            "spx": fetch_ohlcv("^GSPC", period=period)}


def compute_breadth(sample=60, period="1y"):
    """% of a sample of S&P names trading above their 50-day MA. Best-effort."""
    tickers = get_sp500_tickers()[:sample]
    above = total = 0
    for t in tickers:
        df = fetch_ohlcv(t, period=period)
        if df.empty or len(df) < 50:
            continue
        ma = sma(df["close"], 50).iloc[-1]
        if pd.isna(ma):
            continue
        total += 1
        if float(df["close"].iloc[-1]) > float(ma):
            above += 1
    return round(100 * above / total, 1) if total else None


def build_data(ticker, period="3y", with_market=True, with_breadth=False):
    data = {"bars": load_ticker_bars(ticker, period=period)}
    if with_market:
        data.update(load_market())
        if with_breadth:
            data["breadth_pct"] = compute_breadth()
    return data
