from gates import g6_8_options_flow as g


def test_no_options_neutral():
    assert g.check("X", {}).score == 5.0
    assert g.check("X", {"options": None}).score == 5.0


def test_thin_market_neutral():
    res = g.check("X", {"options": {"total_volume": 50,
                                    "call_put_volume_ratio": 9.0}})
    assert res.score == 5.0
    assert "no liquid options" in res.reasoning


def test_bullish_call_buying():
    res = g.check("X", {"options": {"total_volume": 5000,
                                    "call_put_volume_ratio": 2.5}})
    assert res.score == 8.0
    assert "bullish" in res.reasoning


def test_bearish_put_buying():
    res = g.check("X", {"options": {"total_volume": 5000,
                                    "call_put_volume_ratio": 0.4}})
    assert res.score == 2.0
    assert "bearish" in res.reasoning
