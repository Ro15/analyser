import numpy as np

from engine.structuring import build_plan
from tests.conftest import _frame


def _data(seed=0):
    rng = np.random.default_rng(seed)
    closes = 50 + np.cumsum(rng.normal(0.1, 1, 200))
    return {"bars": _frame(np.abs(closes) + 10)}


def test_target_is_20pct_from_config():
    plan = build_plan("NVDA", _data(1))
    assert plan["target_pct"] == 0.20
    assert plan["target"] == round(plan["reference_price"] * 1.20, 2)
    assert "+20%" in plan["scale_out"]


def test_plan_carries_size_and_probability():
    plan = build_plan("NVDA", _data(2), conviction=7, probability=0.44, size="half")
    assert plan["size"] == "half"
    assert plan["p_target_90d"] == 0.44
    assert plan["conviction"] == 7
    assert "probability_15pct_90d" not in plan
