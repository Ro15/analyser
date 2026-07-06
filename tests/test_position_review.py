import datetime as dt

import numpy as np

from journal import position_review, tracker
from tests.conftest import _frame


def _seed_open(tmp_path, monkeypatch, ticker="ADTN"):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    plan = {"ticker": ticker, "entry_zone": [95.0, 102.0],
            "reference_price": 100.0, "target": 120.0,
            "time_stop": "2099-01-01",
            "catalyst": {"type": "earnings", "date": "2026-06-01",
                         "days_out": 10, "description": "ER"}}
    return tracker.log_alert(plan, pipeline_version=2,
                             kill_condition="catalyst cancelled")


def _weak_bars():
    # steady downtrend: last close far below the 50DMA
    closes = np.linspace(100, 70, 120)
    closes[-1] = 60.0
    return _frame(closes)


def _spiky_short():
    return {"short_pct": [0.30] * 9 + [0.60]}


def test_two_flags_and_dead_thesis_closes(tmp_path, monkeypatch):
    _seed_open(tmp_path, monkeypatch)
    monkeypatch.setattr("journal.position_review.data_cache.get",
                        lambda t, period="1y": _weak_bars())
    monkeypatch.setattr("journal.position_review.openbb_source.short_volume",
                        lambda t: _spiky_short())
    monkeypatch.setattr("journal.position_review.llm_client.call_claude",
                        lambda *a, **k: '{"thesis_dead": true, "reasoning": "gone"}')
    out = position_review.review_open_positions(verbose=False,
                                                today=dt.date(2026, 7, 6))
    assert len(out["exits"]) == 1
    rec = tracker.all_alerts()[0]
    assert rec["status"] == "closed"
    assert rec["resolution"] == "thesis_broken"
    assert rec["realized_return"] == (60.0 / 100.0) - 1


def test_no_llm_never_closes(tmp_path, monkeypatch):
    _seed_open(tmp_path, monkeypatch)
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("journal.position_review.data_cache.get",
                        lambda t, period="1y": _weak_bars())
    monkeypatch.setattr("journal.position_review.openbb_source.short_volume",
                        lambda t: _spiky_short())
    out = position_review.review_open_positions(verbose=False,
                                                today=dt.date(2026, 7, 6))
    assert not out["exits"] and len(out["flagged"]) == 1
    assert tracker.all_alerts()[0]["status"] == "open"


def test_below_min_flags_never_asks_judge(tmp_path, monkeypatch):
    _seed_open(tmp_path, monkeypatch)
    # healthy uptrend bars, calm shorts -> at most the catalyst flag
    up = _frame(50 + np.linspace(0, 60, 400))
    monkeypatch.setattr("journal.position_review.data_cache.get",
                        lambda t, period="1y": up)
    monkeypatch.setattr("journal.position_review.openbb_source.short_volume",
                        lambda t: {"short_pct": [0.30] * 10})

    def _boom(*a, **k):
        raise AssertionError("judge must not be called")

    monkeypatch.setattr("journal.position_review.llm_client.call_claude", _boom)
    monkeypatch.setattr("journal.position_review.llm_client.call_deepseek", _boom)
    out = position_review.review_open_positions(verbose=False,
                                                today=dt.date(2026, 7, 6))
    assert not out["exits"]
    assert tracker.all_alerts()[0]["status"] == "open"
