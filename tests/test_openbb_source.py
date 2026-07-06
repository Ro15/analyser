import pandas as pd
import pytest

from data.ingest import openbb_source as obs


def _chain():
    # 2 expiries x call/put; strikes straddle spot=100
    return pd.DataFrame({
        "expiration": ["2026-08-21"] * 4 + ["2026-09-18"] * 4,
        "option_type": ["call", "call", "put", "put"] * 2,
        "strike": [95, 105, 95, 105] * 2,
        "last_trade_price": [7.0, 3.0, 2.0, 6.0, 9.0, 5.0, 4.0, 8.0],
        "volume": [100, 200, 50, 50, 10, 10, 10, 10],
    })


def test_flow_metrics_ratio():
    total, ratio = obs._flow_metrics(_chain())
    assert total == 440
    assert ratio == pytest.approx((100 + 200 + 10 + 10) / (50 + 50 + 10 + 10))


def test_flow_metrics_empty():
    assert obs._flow_metrics(pd.DataFrame()) == (0, None)


def test_expected_move_picks_post_catalyst_expiry():
    # catalyst 2026-09-01 -> first expiry on/after is 2026-09-18
    pct, expiry = obs._expected_move(_chain(), spot=100.0, after_date="2026-09-01")
    assert expiry == "2026-09-18"
    # ATM: strikes 95/105 tie by distance; idxmin picks the first (95):
    # call 9.0 + put 4.0 = 13 -> 13%
    assert pct == pytest.approx(0.13)


def test_expected_move_no_expiry_left():
    pct, expiry = obs._expected_move(_chain(), spot=100.0, after_date="2027-01-01")
    assert pct is None and expiry is None


def test_cache_roundtrip_and_fetch_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(obs, "_CACHE_DIR", str(tmp_path))
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        return {"short_pct": [0.4, 0.5]}

    assert obs._fetch("short_volume", "TEST", _fn) == {"short_pct": [0.4, 0.5]}
    assert obs._fetch("short_volume", "TEST", _fn) == {"short_pct": [0.4, 0.5]}
    assert calls["n"] == 1  # second hit came from cache

    def _boom():
        raise RuntimeError("provider down")

    assert obs._fetch("options", "TEST", _boom) is None
