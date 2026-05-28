import numpy as np
import pandas as pd

from gates import g0_regime
from tests.conftest import _frame, maybe_live


def _spx_above_ma():
    return _frame(50 + np.linspace(0, 40, 300))  # rising -> last > 200DMA


def _spx_below_ma():
    return _frame(120 - np.linspace(0, 60, 300))  # falling -> last < 200DMA


def _vix(level):
    return _frame(np.full(300, float(level)))


def test_regime_pass_calm_market():
    res = g0_regime.check("MARKET", {"vix": _vix(15), "spx": _spx_above_ma()})
    assert res.passed
    assert res.score > 0


def test_regime_fail_high_vix():
    res = g0_regime.check("MARKET", {"vix": _vix(35), "spx": _spx_above_ma()})
    assert not res.passed
    assert "VIX" in res.reasoning


def test_regime_fail_spx_below_200dma():
    res = g0_regime.check("MARKET", {"vix": _vix(15), "spx": _spx_below_ma()})
    assert not res.passed
    assert "200DMA" in res.reasoning


def test_regime_missing_data():
    res = g0_regime.check("MARKET", {"vix": pd.DataFrame(), "spx": pd.DataFrame()})
    assert not res.passed


def test_regime_live_smoke():
    data = {"vix": maybe_live("^VIX"), "spx": maybe_live("^GSPC")}
    res = g0_regime.check("MARKET", data)
    assert isinstance(res.passed, bool)
    assert 0 <= res.score <= 10
