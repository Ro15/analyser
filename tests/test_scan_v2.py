import numpy as np

import scan
from engine.types import GateResult
from tests.conftest import _frame


def _survivor(ticker="NVDA"):
    bars = _frame(50 + np.linspace(0, 60, 400))
    return {"ticker": ticker, "sector": "Tech", "total": 50.0, "vote": 8.0,
            "catalyst": {"type": "earnings", "date": "2026-08-10",
                         "days_out": 35, "description": "ER"},
            "scores": {"g2_trend": 8.0}, "reasonings": {"g5_setups": "VCP"},
            "_data": {"bars": bars}}


def _finalist(ticker="NVDA", passed=True):
    return {"ticker": ticker, "total": 50.0, "sector": "Tech",
            "catalyst": {"type": "earnings", "date": "2026-08-10"},
            "news": GateResult(True, 8.0, "news ok"),
            "sentiment": GateResult(True, 5.0, "calm"),
            "debate": {"verdict": "take", "conviction": 7, "p_target_90d": 0.44,
                       "size": "half", "kill_condition": "catalyst dies",
                       "bull_case": "b", "bear_case": "r", "reasoning": "ok",
                       "used": "Claude"},
            "llm_passed": passed}


def _wire(monkeypatch, tmp_path, survivors, finalists):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    monkeypatch.setenv("LLM_MOCK", "1")
    monkeypatch.setattr(scan.funnel, "run",
                        lambda **k: {"regime": GateResult(True, 8.0, "ok"),
                                     "survivors": survivors})
    monkeypatch.setattr(scan.enrichment, "enrich_finalists",
                        lambda s, n: s[:n])
    monkeypatch.setattr(scan.funnel, "run_finalist_gates",
                        lambda s, verbose=True: (s, []))
    monkeypatch.setattr(scan.funnel, "run_llm_stage",
                        lambda s, verbose=True: {"finalists": finalists,
                                                 "propagated": {}})
    monkeypatch.setattr(scan.relationship_map, "read_through", lambda t: [])
    monkeypatch.setattr(scan.thesis, "generate", lambda *a, **k: "thesis")
    monkeypatch.setattr(scan.position_review, "review_open_positions",
                        lambda verbose=True: {"exits": [], "flagged": []})
    monkeypatch.setattr(scan.postmortem, "run", lambda verbose=True: 0)
    monkeypatch.setattr(scan.tuner, "tune", lambda: {"status": "skip"})
    monkeypatch.setattr(scan.digest, "portfolio_pulse",
                        lambda: "no positions yet")


def test_empty_night_still_sends_digest(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [], [])
    out = scan.run_scan(universe=["X"], dry_run=True, verbose=False)
    assert "Nightly digest" in out["digest"]
    assert not out["buys"]


def test_buy_night_journals_v2(monkeypatch, tmp_path):
    from journal import tracker
    _wire(monkeypatch, tmp_path, [_survivor()], [_finalist()])
    out = scan.run_scan(universe=["NVDA"], dry_run=True, verbose=False)
    assert len(out["buys"]) == 1
    assert "NVDA" in out["buys"][0]
    recs = tracker.all_alerts()
    assert len(recs) == 1
    assert recs[0]["pipeline_version"] == 2
    assert recs[0]["size"] == "half"
    assert recs[0]["kill_condition"] == "catalyst dies"


def test_shadow_never_writes_journal(monkeypatch, tmp_path):
    from journal import tracker
    _wire(monkeypatch, tmp_path, [_survivor()], [_finalist()])
    out = scan.run_scan(universe=["NVDA"], dry_run=True, shadow=True,
                        verbose=False)
    assert "[SHADOW]" in out["digest"]
    assert len(out["buys"]) == 1        # still shows what it WOULD do
    assert tracker.all_alerts() == []   # but journals nothing


def test_rejected_finalists_go_to_watchlist(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [_survivor("AMD")],
          [_finalist("AMD", passed=False)])
    out = scan.run_scan(universe=["AMD"], dry_run=True, verbose=False)
    assert not out["buys"]
    assert "Watchlist" in out["digest"] and "AMD" in out["digest"]
