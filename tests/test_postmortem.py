from journal import playbook, postmortem, tracker


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    monkeypatch.setenv("PLAYBOOK_PATH", str(tmp_path / "pb.md"))
    plan = {"ticker": "CASY", "entry_zone": [95.0, 102.0],
            "reference_price": 100.0, "target": 120.0,
            "time_stop": "2026-06-19", "catalyst": None}
    rec = tracker.log_alert(plan, scores={"g2_trend": 9.0}, pipeline_version=2)
    tracker.resolve(rec["id"], resolution="hit_target", realized_return=0.21)
    return rec


def test_postmortem_writes_lesson_and_marks_done(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setenv("LLM_MOCK", "1")
    n = postmortem.run(verbose=False)
    assert n == 1
    assert "CASY" in playbook.lessons_text()
    assert tracker.all_alerts()[0]["postmortem_done"] is True
    assert postmortem.run(verbose=False) == 0  # idempotent


def test_postmortem_skips_when_no_llm(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert postmortem.run(verbose=False) == 0
    assert tracker.all_alerts()[0]["postmortem_done"] is False
