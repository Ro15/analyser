"""Helpers to build yfinance-style financial-statement DataFrames for tests.

Rows are line items, columns are periods (newest first), matching yfinance's
.income_stmt / .cashflow / .balance_sheet layout.
"""
import pandas as pd


def fin(rows, periods=4):
    cols = pd.bdate_range(end="2025-12-31", periods=periods, freq="YE")[::-1]
    return pd.DataFrame({c: [vals[i] for vals in rows.values()]
                         for i, c in enumerate(cols)},
                        index=list(rows.keys()))
