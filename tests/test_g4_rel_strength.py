import numpy as np

from gates import g4_relative_strength
from tests.conftest import _frame


def test_rs_high_passes():
    strong = _frame(50 + np.linspace(0, 60, 200))      # big trailing gain
    weak_etf = _frame(50 + np.linspace(0, 2, 200))      # sector lags
    universe = list(np.linspace(-0.2, 0.1, 50))         # most names below strong
    data = {"bars": strong, "rs_universe_returns": universe,
            "sector": "Technology", "sector_etf_bars": {"XLK": weak_etf}}
    res = g4_relative_strength.check("X", data)
    assert res.passed
    assert "RS" in res.reasoning


def test_rs_low_fails():
    weak = _frame(60 - np.linspace(0, 20, 200))         # negative trailing return
    strong_etf = _frame(50 + np.linspace(0, 40, 200))
    universe = list(np.linspace(0.1, 0.6, 50))          # everyone beats it
    data = {"bars": weak, "rs_universe_returns": universe,
            "sector": "Technology", "sector_etf_bars": {"XLK": strong_etf}}
    res = g4_relative_strength.check("X", data)
    assert not res.passed
