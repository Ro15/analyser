"""Cached access to yfinance fundamentals (info, financials, cashflow, calendar).

Everything is best-effort: network/parse failures return None and gates degrade
to a neutral verdict rather than crashing. yfinance gives CURRENT fundamentals
only (no point-in-time), a limitation the valuation gate calls out explicitly.
"""
import functools

import yfinance as yf


@functools.lru_cache(maxsize=256)
def _ticker(symbol):
    return yf.Ticker(symbol)


@functools.lru_cache(maxsize=256)
def info(symbol):
    try:
        return _ticker(symbol).info or {}
    except Exception:
        return {}


@functools.lru_cache(maxsize=256)
def income_stmt(symbol):
    try:
        return _ticker(symbol).income_stmt
    except Exception:
        return None


@functools.lru_cache(maxsize=256)
def cashflow(symbol):
    try:
        return _ticker(symbol).cashflow
    except Exception:
        return None


@functools.lru_cache(maxsize=256)
def balance_sheet(symbol):
    try:
        return _ticker(symbol).balance_sheet
    except Exception:
        return None


@functools.lru_cache(maxsize=256)
def earnings_dates(symbol):
    try:
        return _ticker(symbol).get_earnings_dates(limit=12)
    except Exception:
        return None


def row(df, *names):
    """First matching row of a financials DataFrame as a list (newest first)."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return list(df.loc[n].values)
    return None
