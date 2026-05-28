import numpy as np

from gates import g5_3_priced_in
from tests.conftest import _frame


def test_priced_in_rejects_big_runup():
    closes = np.concatenate([np.full(50, 50.0), np.linspace(50, 62, 22)])  # +24% in ~1mo
    res = g5_3_priced_in.check("X", {"bars": _frame(closes)})
    assert not res.passed
    assert "priced in" in res.reasoning.lower()


def test_room_to_run_passes_flat():
    closes = np.concatenate([np.full(50, 50.0), np.full(22, 50.5)])  # ~flat
    res = g5_3_priced_in.check("X", {"bars": _frame(closes)})
    assert res.passed
    assert res.score > 8
