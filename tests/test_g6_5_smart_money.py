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
