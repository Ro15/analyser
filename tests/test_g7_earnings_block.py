import pandas as pd

from gates import g7_earnings_block


def _earnings_df(days_out_list):
    idx = pd.DatetimeIndex([pd.Timestamp.now().normalize() + pd.Timedelta(days=d)
                            for d in days_out_list])
    return pd.DataFrame({"EPS Estimate": [1.0] * len(idx)}, index=idx)


def test_earnings_within_blackout_rejected():
    res = g7_earnings_block.check("X", {"earnings_dates": _earnings_df([5])})
    assert not res.passed
    assert "blackout" in res.reasoning


def test_earnings_in_hold_window_flagged_but_passes():
    res = g7_earnings_block.check("X", {"earnings_dates": _earnings_df([45])})
    assert res.passed
    assert "hold window" in res.reasoning


def test_earnings_far_out_passes():
    res = g7_earnings_block.check("X", {"earnings_dates": _earnings_df([200])})
    assert res.passed


def test_earnings_unknown_passes():
    res = g7_earnings_block.check("X", {"earnings_dates": None})
    assert res.passed
