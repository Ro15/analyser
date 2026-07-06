import pytest

from engine import debate, llm_client


def _ctx():
    return {"sector": "Tech", "gate_scores": {"g2_trend": 8.0},
            "catalyst": {"type": "earnings", "date": "2026-08-10"},
            "setup": "VCP", "news_summary": "positive",
            "consensus": {"target_consensus": 130.0},
            "short_interest": {"days_to_cover": 6.0},
            "options": {"call_put_volume_ratio": 2.5, "expected_move_pct": 0.08},
            "playbook": "(1 lessons, newest first)\n- [x] mock lesson"}


def test_mock_debate_full_shape(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    res = debate.run_debate("NVDA", _ctx())
    assert res["verdict"] == "take"
    assert res["conviction"] == 7
    assert res["p_target_90d"] == pytest.approx(0.44)
    assert res["size"] == "half"
    assert isinstance(res["kill_condition"], str) and res["kill_condition"]
    assert res["bull_case"] and res["bear_case"]
    assert res["used"] == "Claude"


def test_no_models_returns_unvetted(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    res = debate.run_debate("NVDA", _ctx())
    assert res["verdict"] == "unvetted"
    assert res["size"] is None


def test_garbage_judge_output_is_unvetted(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.setattr(llm_client, "call_deepseek",
                        lambda *a, **k: '{"case": "meh"}')
    monkeypatch.setattr(llm_client, "call_claude",
                        lambda *a, **k: "I refuse to answer in JSON")
    res = debate.run_debate("NVDA", _ctx())
    assert res["verdict"] == "unvetted"
