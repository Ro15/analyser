from gates import g1_liquidity
from tests.conftest import maybe_live


def test_liquidity_pass(uptrend_bars):
    # ~$110 * 5M shares = ~$550M ADV, well above $10M floor.
    res = g1_liquidity.check("TEST", {"bars": uptrend_bars})
    assert res.passed
    assert res.score > 0


def test_liquidity_fail_illiquid(illiquid_bars):
    res = g1_liquidity.check("TEST", {"bars": illiquid_bars})
    assert not res.passed
    # $4 price < $10 min AND $200K ADV < $10M.
    assert "price" in res.reasoning or "ADV" in res.reasoning


def test_liquidity_live_aapl():
    res = g1_liquidity.check("AAPL", {"bars": maybe_live("AAPL")})
    assert res.passed  # AAPL is unambiguously liquid
