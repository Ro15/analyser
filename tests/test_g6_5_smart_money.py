from gates import g6_5_smart_money


def test_insider_cluster_boosts():
    data = {"form4_count": 6, "info": {"heldPercentInstitutions": 0.8}}
    res = g6_5_smart_money.check("X", data)
    assert res.passed  # pass-through gate
    assert res.score > 6
    assert "cluster" in res.reasoning


def test_no_data_neutral():
    data = {"form4_count": None, "info": {}}
    res = g6_5_smart_money.check("X", data)
    assert res.passed
    assert res.score == 5.0


def test_insider_buy_cluster_boosts():
    base = {"form4_count": 0, "info": {}}
    plain = g6_5_smart_money.check("X", base)
    boosted = g6_5_smart_money.check("X", {**base, "insider": {"buys": 3, "sells": 0}})
    assert boosted.score == plain.score + 2.0
    assert "buying cluster" in boosted.reasoning


def test_heavy_insider_selling_penalized():
    base = {"form4_count": 0, "info": {}}
    plain = g6_5_smart_money.check("X", base)
    hit = g6_5_smart_money.check("X", {**base, "insider": {"buys": 0, "sells": 4}})
    assert hit.score == max(0.0, plain.score - 2.0)
    assert "selling" in hit.reasoning
