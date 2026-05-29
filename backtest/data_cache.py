"""Fetch each ticker's history and cache it (in-memory + on-disk parquet).

On-disk cache lives under .cache/ (gitignored). Backtests reuse it forever
(history doesn't change). LIVE scans pass `max_age_hours` so stale prices get
refreshed -- otherwise a nightly run would keep scanning yesterday's prices.
"""
import os
import time

import pandas as pd

from data.ingest.prices import fetch_ohlcv

_CACHE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, ".cache")
_MEM = {}

# Default freshness for live scans: refresh prices older than this.
LIVE_MAX_AGE_HOURS = 18


def _path(ticker, period):
    return os.path.join(_CACHE_DIR, f"{ticker.replace('/', '_')}_{period}.parquet")


def _is_fresh(path, max_age_hours):
    """True if the cached file is fresh enough (None => never expires)."""
    if max_age_hours is None:
        return True
    return (time.time() - os.path.getmtime(path)) < max_age_hours * 3600


def get(ticker, period="3y", max_age_hours=None):
    key = (ticker, period)
    if key in _MEM:
        return _MEM[key]

    os.makedirs(_CACHE_DIR, exist_ok=True)
    p = _path(ticker, period)
    if os.path.exists(p) and _is_fresh(p, max_age_hours):
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


def prefetch_bulk(tickers, period="3y", max_age_hours=LIVE_MAX_AGE_HOURS):
    """Warm the cache for many tickers in one shot via Alpaca SIP bulk.

    Fetches tickers that are missing OR whose cached prices are older than
    `max_age_hours` (so nightly runs refresh). Anything Alpaca misses is left
    for the per-ticker get() fallback. This is what makes a full-universe
    (thousands of names) scan fast while keeping prices fresh.
    """
    from data.ingest import alpaca_source
    if not alpaca_source.is_configured():
        return
    need = []
    for t in tickers:
        if (t, period) in _MEM:
            continue
        p = _path(t, period)
        if os.path.exists(p) and _is_fresh(p, max_age_hours):
            continue
        need.append(t)
    if not need:
        return
    try:
        got = alpaca_source.fetch_many(need, period=period)
    except Exception:
        return  # leave them for the per-ticker fallback
    os.makedirs(_CACHE_DIR, exist_ok=True)
    for t, df in got.items():
        if df is None or df.empty:
            continue
        _MEM[(t, period)] = df
        try:
            df.to_parquet(_path(t, period))
        except Exception:
            pass
