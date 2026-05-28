from gates import g7_5_earnings_quality
from tests.conftest_fin import fin


def test_multiple_red_flags_rejected():
    inc = fin({"Net Income": [100, 90, 80, 70], "Total Revenue": [500, 480, 460, 440]})
    cf = fin({"Operating Cash Flow": [40, 50, 45, 40],          # CFO/NI 0.4 < 0.7
              "Stock Based Compensation": [100, 90, 80, 70],    # 20% of rev
              "Repurchase Of Capital Stock": [-50, -40, -30, -20]})
    bs = fin({"Accounts Receivable": [200, 120, 110, 100],      # DSO spiking
              "Total Debt": [800, 600, 500, 400]})              # debt rising w/ buyback
    res = g7_5_earnings_quality.check("X", {"income_stmt": inc, "cashflow": cf,
                                            "balance_sheet": bs})
    assert not res.passed
    assert "REJECT" in res.reasoning


def test_clean_books_pass():
    inc = fin({"Net Income": [100, 90, 80, 70], "Total Revenue": [500, 480, 460, 440]})
    cf = fin({"Operating Cash Flow": [120, 110, 95, 80],        # CFO > NI
              "Stock Based Compensation": [20, 18, 16, 14],     # ~4% of rev
              "Repurchase Of Capital Stock": [-50, -40, -30, -20]})
    bs = fin({"Accounts Receivable": [100, 98, 95, 92],         # DSO stable
              "Total Debt": [380, 400, 410, 420]})              # debt falling
    res = g7_5_earnings_quality.check("X", {"income_stmt": inc, "cashflow": cf,
                                            "balance_sheet": bs})
    assert res.passed


def test_missing_statements_neutral():
    res = g7_5_earnings_quality.check("X", {"income_stmt": None, "cashflow": None,
                                            "balance_sheet": None})
    assert res.passed and res.score == 5.0
