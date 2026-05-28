"""Fetch each ticker's full history once and cache it (in-memory + on-disk).

On-disk cache lives under .cache/ (gitignored) as parquet so repeated backtest
runs don't hammer yfinance.
"""
import os

import pandas as pd

from data.ingest.prices import fetch_ohlcv

_CACHE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, ".cache")
_MEM = {}


def _path(ticker, period):
    return os.path.join(_CACHE_DIR, f"{ticker.replace('/', '_')}_{period}.parquet")


def get(ticker, period="3y"):
    key = (ticker, period)
    if key in _MEM:
        return _MEM[key]

    os.makedirs(_CACHE_DIR, exist_ok=True)
    p = _path(ticker, period)
    if os.path.exists(p):
        try:
            df = pd.read_parquet(p)
            _MEM[key] = df
            return df
        except Exception:
            pass

    df = fetch_ohlcv(ticker, period=period)
    if not df.empty:
        try:
            df.to_parquet(p)
        except Exception:
            pass  # parquet engine optional; in-memory cache still works
    _MEM[key] = df
    return df


def prefetch(tickers, period="3y"):
    out = {}
    for t in tickers:
        df = get(t, period=period)
        if not df.empty:
            out[t] = df
    return out
