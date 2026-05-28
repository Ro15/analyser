import numpy as np

from gates import g6_volume_flow
from tests.conftest import _frame


def test_accumulation_passes():
    # Rising price with heavier volume on up days -> OBV rising, up>down vol.
    closes = 50 + np.linspace(0, 10, 60)
    vols = np.full(60, 1_000_000.0)
    vols[1::2] = 2_000_000.0  # heavier volume distributed across rising days
    res = g6_volume_flow.check("X", {"bars": _frame(closes, vols)})
    assert res.passed
    assert "Accumulation" in res.reasoning


def test_declining_volume_rejected():
    # Drifting price but volume drying up sharply and OBV flat/falling.
    closes = 50 - np.linspace(0, 5, 60)
    vols = np.concatenate([np.full(25, 3_000_000.0), np.full(35, 500_000.0)])
    res = g6_volume_flow.check("X", {"bars": _frame(closes, vols)})
    assert not res.passed
