from gates import g5_setups
from tests.conftest import maybe_live


def test_breakout_setup(breakout_bars):
    res = g5_setups.check("TEST", {"bars": breakout_bars})
    assert res.passed
    assert "breakout" in res.reasoning.lower()
    assert 0 < res.score <= 10


def test_pullback_setup(pullback_bars):
    res = g5_setups.check("TEST", {"bars": pullback_bars})
    assert res.passed
    assert "pullback" in res.reasoning.lower()


def test_no_setup_on_downtrend(downtrend_bars):
    res = g5_setups.check("TEST", {"bars": downtrend_bars})
    assert not res.passed
    assert "No setup" in res.reasoning


def test_setups_live_smoke():
    res = g5_setups.check("NVDA", {"bars": maybe_live("NVDA", period="2y")})
    assert isinstance(res.passed, bool)
    assert 0 <= res.score <= 10
