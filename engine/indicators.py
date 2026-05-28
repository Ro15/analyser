"""Shared technical-indicator helpers used across gates.

All functions take/return pandas objects and assume a bars DataFrame with
lowercase columns: open/high/low/close/volume, indexed by ascending date.
"""
import numpy as np
import pandas as pd


def sma(series, window):
    return series.rolling(window).mean()


def ma_slope(ma, lookback):
    """Fractional change of an MA over `lookback` bars (>0 == rising)."""
    if len(ma.dropna()) <= lookback:
        return np.nan
    cur = ma.iloc[-1]
    prev = ma.iloc[-1 - lookback]
    if prev is None or pd.isna(prev) or prev == 0:
        return np.nan
    return (cur - prev) / prev


def atr(bars, window=14):
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(window).mean()


def obv(bars):
    """On-balance volume."""
    direction = np.sign(bars["close"].diff().fillna(0))
    return (direction * bars["volume"]).cumsum()


def dollar_volume(bars, window=20):
    return (bars["close"] * bars["volume"]).rolling(window).mean()
