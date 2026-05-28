from gates import g5_7_fundamentals
from tests.conftest_fin import fin


def test_fundamentals_pass_healthy():
    inc = fin({"Total Revenue": [120, 100, 85, 75],
               "Gross Profit": [60, 48, 40, 34]})
    cf = fin({"Free Cash Flow": [30, 22, 18, 12]})
    res = g5_7_fundamentals.check("X", {"income_stmt": inc, "cashflow": cf})
    assert res.passed
    assert "OK" in res.reasoning


def test_fundamentals_fail_declining():
    inc = fin({"Total Revenue": [80, 100, 110, 115],     # shrinking
               "Gross Profit": [24, 40, 50, 58]})         # margin collapsing
    cf = fin({"Free Cash Flow": [-5, 10, 15, 20]})        # FCF turned negative
    res = g5_7_fundamentals.check("X", {"income_stmt": inc, "cashflow": cf})
    assert not res.passed


def test_fundamentals_neutral_when_missing():
    res = g5_7_fundamentals.check("X", {"income_stmt": None, "cashflow": None})
    assert res.passed and res.score == 5.0
