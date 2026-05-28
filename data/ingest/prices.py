"""Pull daily OHLCV via yfinance and (optionally) store into Postgres.

Handles yfinance rate limits with batching + exponential-backoff retry.
"""
import time

import pandas as pd
import yfinance as yf

from data import store


def _normalize(df):
    """Normalize a yfinance OHLCV frame to lowercase open/high/low/close/volume."""
    if df is None or df.empty:
        return pd.DataFrame()
    # yfinance can return a MultiIndex (single-ticker download) -> flatten.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df.dropna(how="all")


def fetch_ohlcv(ticker, period="3y", interval="1d", retries=4):
    """Fetch normalized OHLCV for one ticker, with exponential-backoff retry."""
    delay = 2
    for attempt in range(retries):
        try:
            raw = yf.Ticker(ticker).history(
                period=period, interval=interval, auto_adjust=True
            )
            df = _normalize(raw)
            if not df.empty:
                return df
        except Exception as e:  # noqa: BLE001
            print(f"[prices] {ticker} attempt {attempt + 1} failed: {e}")
        time.sleep(delay)
        delay *= 2
    print(f"[prices] {ticker}: no data after {retries} attempts.")
    return pd.DataFrame()


def ingest_universe(tickers, period="3y", batch_size=25, to_db=True):
    """Fetch a universe of tickers in batches and upsert into daily_bars.

    Returns {ticker: rows_written}. Skips DB writes if Postgres is unavailable.
    """
    have_db = to_db and store.is_available()
    if to_db and not have_db:
        print("[prices] Postgres unavailable -> fetching only, not persisting.")
    if have_db:
        store.create_tables()

    results = {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        print(f"[prices] batch {i // batch_size + 1}: {batch[0]}..{batch[-1]}")
        for t in batch:
            df = fetch_ohlcv(t, period=period)
            results[t] = store.upsert_bars(t, df) if have_db else len(df)
        time.sleep(2)  # be polite to yahoo between batches
    return results


if __name__ == "__main__":
    import sys

    syms = sys.argv[1:] or ["AAPL"]
    print(ingest_universe(syms, period="6mo"))
