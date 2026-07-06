from gates import g6_7_short_pressure as g


def test_no_data_is_neutral():
    res = g.check("X", {})
    assert res.passed and res.score == 5.0


def test_rising_short_volume_penalized():
    data = {"short_volume": {"short_pct": [0.30] * 7 + [0.50] * 3}}
    res = g.check("X", data)
    assert res.passed
    assert res.score == 2.0
    assert "rising" in res.reasoning


def test_falling_short_volume_rewarded():
    data = {"short_volume": {"short_pct": [0.50] * 7 + [0.30] * 3}}
    res = g.check("X", data)
    assert res.score == 7.0
    assert "drying up" in res.reasoning


def test_squeeze_fuel_bonus_needs_strong_fundamentals():
    base = {"short_interest": {"days_to_cover": 6.0, "current": 1, "previous": 1}}
    weak = g.check("X", {**base, "gate_scores": {"g5.7_fundamentals": 4.0}})
    strong = g.check("X", {**base, "gate_scores": {"g5.7_fundamentals": 8.0}})
    assert weak.score == 5.0
    assert strong.score == 7.0
    assert "squeeze" in strong.reasoning
