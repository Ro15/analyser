import numpy as np

from gates import g3_sector
from engine.sectors import ALL_SECTOR_ETFS
from tests.conftest import _frame


def _etf_bars(strength):
    # Higher strength -> steeper rise -> higher momentum.
    return _frame(50 + np.linspace(0, strength, 80))


def _all_etfs(top_etf):
    bars = {}
    for i, e in enumerate(ALL_SECTOR_ETFS):
        bars[e] = _etf_bars(40 if e == top_etf else 2 + i * 0.1)
    return bars


def test_sector_top4_passes():
    data = {"sector": "Technology", "sector_etf_bars": _all_etfs("XLK")}
    res = g3_sector.check("X", data)
    assert res.passed and "top-4" in res.reasoning


def test_sector_outside_top4_rejected():
    # XLK weakest, no strong own bars -> reject.
    etfs = _all_etfs("XLF")
    etfs["XLK"] = _frame(60 - np.linspace(0, 20, 80))  # falling
    data = {"sector": "Technology", "sector_etf_bars": etfs,
            "bars": _frame(50 + np.linspace(0, 1, 80))}
    res = g3_sector.check("X", data)
    assert not res.passed


def test_individual_strength_override():
    etfs = _all_etfs("XLF")
    etfs["XLK"] = _frame(60 - np.linspace(0, 20, 80))
    strong = _frame(np.concatenate([np.full(20, 50.0), np.linspace(50, 70, 60)]))
    data = {"sector": "Technology", "sector_etf_bars": etfs, "bars": strong}
    res = g3_sector.check("X", data)
    assert res.passed and "override" in res.reasoning
