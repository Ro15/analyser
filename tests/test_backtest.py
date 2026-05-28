import numpy as np
import pandas as pd
import pytest

from backtest import harness, metrics
from tests.conftest import _frame


def test_no_lookahead_slice():
    df = _frame(np.linspace(10, 20, 300))
    asof = df.index[100]
    sliced = harness._slice(df, asof)
    assert sliced.index[-1] == asof
    assert len(sliced) == 101
    harness._assert_no_lookahead(sliced, asof)  # must not raise


def test_forward_return_uses_future_only():
    # Price doubles after entry -> positive forward return.
    closes = np.concatenate([np.full(100, 50.0), np.linspace(50, 100, 200)])
    df = _frame(closes)
    pos = 100
    fwd = harness._forward_return(df, pos, hold_days=90, slippage=0.001)
    assert fwd is not None
    assert fwd["entry_date"] == df.index[pos]
    assert fwd["exit_date"] > fwd["entry_date"]  # exit strictly in the future
    assert fwd["ret"] > 0


def test_forward_return_none_when_insufficient_future():
    df = _frame(np.linspace(10, 20, 120))
    fwd = harness._forward_return(df, len(df) - 1, hold_days=90, slippage=0.001)
    assert fwd is None


def test_metrics_empty():
    assert metrics.compute_metrics(pd.DataFrame())["alerts"] == 0


def test_metrics_basic():
    df = pd.DataFrame({
        "ret": [0.2, -0.1, 0.05],
        "spy_ret": [0.05, 0.02, 0.03],
        "excess": [0.15, -0.12, 0.02],
        "mfe": [0.25, 0.01, 0.16],
    })
    m = metrics.compute_metrics(df)
    assert m["alerts"] == 3
    assert m["win_rate"] == pytest.approx(2 / 3)
    assert m["hit_target_rate"] == pytest.approx(2 / 3)  # 0.25 and 0.16 >= 0.15
