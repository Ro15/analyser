"""Pulls AAPL and confirms rows land in the DB.

Auto-skips when no Postgres is reachable (e.g. ephemeral CI container), so the
suite stays green everywhere while still exercising the real DB path locally.
"""
import pytest

from data import store
from data.ingest.prices import fetch_ohlcv

pytestmark = pytest.mark.skipif(
    not store.is_available(),
    reason="Postgres not reachable; set DB_* in .env to run this test.",
)


def test_aapl_lands_in_db():
    store.create_tables()
    df = fetch_ohlcv("AAPL", period="1mo")
    assert not df.empty, "yfinance returned no AAPL data"

    written = store.upsert_bars("AAPL", df)
    assert written == len(df)

    loaded = store.load_bars("AAPL")
    assert store.count_rows("AAPL") >= len(df)
    assert {"open", "high", "low", "close", "volume"}.issubset(loaded.columns)
