"""Synthetic OHLCV builders for deterministic gate tests, plus a live-fetch
helper that skips when yfinance is unavailable/rate-limited."""
import numpy as np
import pandas as pd
import pytest

from data.ingest.prices import fetch_ohlcv


def _frame(closes, volumes=None):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    idx = pd.bdate_range(end=pd.Timestamp("2025-01-02"), periods=n)
    if volumes is None:
        volumes = np.full(n, 1_000_000.0)
    volumes = np.asarray(volumes, dtype=float)
    high = closes * 1.01
    low = closes * 0.99
    open_ = closes
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": closes, "volume": volumes},
        index=idx,
    )
    df.index.name = "date"
    return df


@pytest.fixture
def uptrend_bars():
    """Steady rising series, price above a rising 200DMA."""
    n = 400
    closes = 50 + np.linspace(0, 60, n) + np.sin(np.linspace(0, 20, n))
    return _frame(closes, volumes=np.full(n, 5_000_000.0))


@pytest.fixture
def downtrend_bars():
    """Steady falling series, price below a declining 200DMA."""
    n = 400
    closes = 120 - np.linspace(0, 70, n) + np.sin(np.linspace(0, 20, n))
    return _frame(closes, volumes=np.full(n, 5_000_000.0))


@pytest.fixture
def pullback_bars():
    """Uptrend then a small dip back toward the rising 50DMA."""
    n = 300
    base = 50 + np.linspace(0, 50, n)
    base[-8:] = base[-9] - np.linspace(0, 2.0, 8)  # shallow pullback
    return _frame(base, volumes=np.full(n, 5_000_000.0))


@pytest.fixture
def breakout_bars():
    """Flat base then a final-bar breakout above prior high on big volume."""
    n = 260
    closes = np.concatenate([
        np.full(200, 50.0) + np.random.default_rng(1).normal(0, 0.3, 200),
        np.full(59, 52.0) + np.random.default_rng(2).normal(0, 0.3, 59),
        [60.0],  # breakout close
    ])
    vols = np.full(n, 2_000_000.0)
    vols[-1] = 8_000_000.0  # volume surge on breakout
    return _frame(closes, volumes=vols)


@pytest.fixture
def illiquid_bars():
    """Penny-ish, thin volume -> should fail liquidity."""
    n = 250
    return _frame(np.full(n, 4.0), volumes=np.full(n, 50_000.0))


def maybe_live(ticker, period="2y"):
    """Fetch live bars or skip the test if yfinance returns nothing."""
    df = fetch_ohlcv(ticker, period=period)
    if df.empty:
        pytest.skip(f"live data for {ticker} unavailable (network/rate limit)")
    return df
