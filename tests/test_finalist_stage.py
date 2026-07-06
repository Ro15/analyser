import numpy as np

from engine import enrichment, funnel
from tests.conftest import _frame


def _survivor(ticker, bars, options=None):
    return {"ticker": ticker, "sector": "Tech", "total": 50.0, "vote": 7.5,
            "catalyst": {"type": "earnings", "date": "2026-08-10", "days_out": 35},
            "scores": {"g2_trend": 8.0, "g5.7_fundamentals": 8.0},
            "reasonings": {},
            "_data": {"bars": bars, "options": options,
                      "short_volume": {"short_pct": [0.5] * 7 + [0.3] * 3},
                      "short_interest": {"days_to_cover": 6.0,
                                         "current": 1, "previous": 1},
                      "insider": {"buys": 3, "sells": 0},
                      "info": {}, "form4_count": 0,
                      "gate_scores": {"g5.7_fundamentals": 8.0}}}


def _flat_bars():
    return _frame(np.full(60, 100.0))


def test_enrich_injects_all_keys(monkeypatch):
    from data.ingest import openbb_source as obs
    monkeypatch.setattr(obs, "short_volume", lambda t: {"short_pct": [0.4]})
    monkeypatch.setattr(obs, "short_interest", lambda t: None)
    monkeypatch.setattr(obs, "options_snapshot", lambda t, catalyst_date=None: None)
    monkeypatch.setattr(obs, "insider_activity", lambda t, days=60: {"buys": 0, "sells": 0})
    monkeypatch.setattr(obs, "analyst_consensus", lambda t: None)
    s = {"ticker": "T", "scores": {"g2_trend": 7.0}, "catalyst": None, "_data": {}}
    out = enrichment.enrich_finalists([s], top_n=1)
    d = out[0]["_data"]
    for key in ("short_volume", "short_interest", "options", "insider",
                "consensus", "gate_scores"):
        assert key in d
    assert d["gate_scores"] == {"g2_trend": 7.0}


def test_finalist_gates_rescore_and_keep():
    s = _survivor("GOOD", _flat_bars(),
                  options={"total_volume": 5000, "call_put_volume_ratio": 2.5,
                           "expected_move_pct": 0.08, "expiry_used": "2026-08-21"})
    kept, dropped = funnel.run_finalist_gates([s], verbose=False)
    assert len(kept) == 1 and not dropped
    for label in ("g5.3_priced_in", "g6.5_smart_money",
                  "g6.7_short_pressure", "g6.8_options_flow"):
        assert label in kept[0]["scores"]
    assert kept[0]["vote"] > 0


def test_finalist_gates_drop_priced_in():
    s = _survivor("LATE", _flat_bars(),
                  options={"total_volume": 5000, "call_put_volume_ratio": 1.0,
                           "expected_move_pct": 0.25, "expiry_used": "2026-08-21"})
    kept, dropped = funnel.run_finalist_gates([s], verbose=False)
    assert not kept and len(dropped) == 1
    assert "drop_reason" in dropped[0]
