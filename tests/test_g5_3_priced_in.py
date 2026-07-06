import numpy as np

from gates import g5_3_priced_in as g
from tests.conftest import _frame


def _flat_bars(n=60, price=100.0):
    return _frame(np.full(n, price))


def _runup_bars(n=60, pct=0.15):
    closes = np.full(n, 100.0)
    closes[-21:] = np.linspace(100, 100 * (1 + pct), 21)
    return _frame(closes)


def test_big_runup_rejected():
    res = g.check("X", {"bars": _runup_bars(pct=0.15)})
    assert not res.passed
    assert "priced in" in res.reasoning.lower()


def test_flat_full_score():
    res = g.check("X", {"bars": _flat_bars()})
    assert res.passed
    assert res.score == 10.0


def test_options_implied_move_at_target_rejects():
    res = g.check("X", {"bars": _flat_bars(),
                        "options": {"expected_move_pct": 0.22,
                                    "expiry_used": "2026-08-21"}})
    assert not res.passed
    assert "options" in res.reasoning.lower()


def test_small_implied_move_confirms_edge():
    res = g.check("X", {"bars": _flat_bars(),
                        "options": {"expected_move_pct": 0.08,
                                    "expiry_used": "2026-08-21"}})
    assert res.passed
    assert res.score == 10.0  # 10 + 2 bonus, capped at 10
    assert "not priced in" in res.reasoning


def test_insufficient_history_fails():
    res = g.check("X", {"bars": _flat_bars(n=10)})
    assert not res.passed
