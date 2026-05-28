"""PostgreSQL interface for daily OHLCV bars.

Credentials are read from .env (never hardcoded). Uses a SEPARATE database
(default: swing_analyzer) so it never touches any existing trading bot's data.
"""
import os
from contextlib import contextmanager

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def db_config():
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "swing_analyzer"),
        user=os.getenv("DB_USER") or os.getenv("USER"),
        password=os.getenv("DB_PASSWORD") or None,
    )


@contextmanager
def get_conn():
    conn = psycopg2.connect(**db_config())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def is_available():
    """True if a Postgres connection can be opened. Lets tests skip cleanly."""
    try:
        with get_conn():
            return True
    except Exception:
        return False


def create_tables():
    ddl = """
    CREATE TABLE IF NOT EXISTS daily_bars (
        ticker  TEXT          NOT NULL,
        date    DATE          NOT NULL,
        open    DOUBLE PRECISION,
        high    DOUBLE PRECISION,
        low     DOUBLE PRECISION,
        close   DOUBLE PRECISION,
        volume  BIGINT,
        PRIMARY KEY (ticker, date)
    );
    CREATE INDEX IF NOT EXISTS idx_daily_bars_ticker ON daily_bars (ticker);
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(ddl)


def upsert_bars(ticker, df):
    """Upsert a DataFrame of OHLCV bars for one ticker.

    df must have a DatetimeIndex (date) and columns open/high/low/close/volume.
    Returns the number of rows written.
    """
    if df is None or df.empty:
        return 0

    rows = []
    for idx, row in df.iterrows():
        rows.append(
            (
                ticker,
                pd.Timestamp(idx).date(),
                _f(row.get("open")),
                _f(row.get("high")),
                _f(row.get("low")),
                _f(row.get("close")),
                _i(row.get("volume")),
            )
        )

    sql = """
        INSERT INTO daily_bars (ticker, date, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (ticker, date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume;
    """
    with get_conn() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows)
    return len(rows)


def load_bars(ticker, start=None, end=None):
    """Return a DataFrame of bars for a ticker, indexed by date (ascending)."""
    sql = "SELECT date, open, high, low, close, volume FROM daily_bars WHERE ticker = %s"
    params = [ticker]
    if start:
        sql += " AND date >= %s"
        params.append(start)
    if end:
        sql += " AND date <= %s"
        params.append(end)
    sql += " ORDER BY date ASC"
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params=params, parse_dates=["date"])
    if not df.empty:
        df = df.set_index("date")
    return df


def count_rows(ticker):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM daily_bars WHERE ticker = %s", (ticker,))
        return cur.fetchone()[0]


def _f(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        if v is None or pd.isna(v):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None
