from gates import g2_trend
from tests.conftest import maybe_live


def test_trend_pass_uptrend(uptrend_bars):
    res = g2_trend.check("TEST", {"bars": uptrend_bars})
    assert res.passed
    assert "Uptrend" in res.reasoning


def test_trend_fail_downtrend(downtrend_bars):
    res = g2_trend.check("TEST", {"bars": downtrend_bars})
    assert not res.passed
    assert "Downtrend" in res.reasoning


def test_trend_insufficient_history():
    from tests.conftest import _frame
    import numpy as np
    res = g2_trend.check("TEST", {"bars": _frame(np.full(50, 10.0))})
    assert not res.passed
    assert "insufficient" in res.reasoning.lower()


def test_trend_live_smoke():
    res = g2_trend.check("AAPL", {"bars": maybe_live("AAPL", period="2y")})
    assert isinstance(res.passed, bool)
