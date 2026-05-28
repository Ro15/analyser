import numpy as np

from gates import g5_5_valuation
from tests.conftest import _frame


def test_valuation_rejects_top_decile():
    # Price ramps to the very top of its multi-year range -> top decile.
    closes = 20 + np.linspace(0, 80, 300)
    res = g5_5_valuation.check("X", {"bars": _frame(closes), "info": {}})
    assert not res.passed
    assert "FOMO" in res.reasoning


def test_valuation_rejects_rich_multiples():
    closes = 50 + np.sin(np.linspace(0, 10, 300))  # mid-range price
    info = {"forwardPE": 80, "priceToSalesTrailing12Months": 30}
    res = g5_5_valuation.check("X", {"bars": _frame(closes), "info": info})
    assert not res.passed


def test_valuation_passes_midrange():
    closes = np.concatenate([np.linspace(20, 100, 250), np.linspace(100, 55, 50)])
    res = g5_5_valuation.check("X", {"bars": _frame(closes), "info": {}})
    assert res.passed
