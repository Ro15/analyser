import json

import numpy as np
import pytest

from engine import llm_client
from gates import g8_news_catalyst, g8_3_propagation, g8_5_sentiment
from tests.conftest import _frame


# ---- llm_client ----

def test_extract_json_plain():
    assert llm_client.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced_with_prose():
    txt = 'Sure!\n```json\n{"verdict": "would take", "conviction": 4}\n```\nDone.'
    assert llm_client.extract_json(txt)["conviction"] == 4


def test_extract_json_garbage():
    assert llm_client.extract_json("no json here") is None


def test_no_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MOCK", raising=False)
    with pytest.raises(llm_client.LLMUnavailable):
        llm_client.call_deepseek("sys", "user")


def test_mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    out = llm_client.extract_json(llm_client.call_claude("sys", "user"))
    assert out["verdict"] == "would take"


# ---- Gate 8 news ----

def test_news_neutral_when_no_headlines(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    res = g8_news_catalyst.check("X", {"headlines": [], "info": {"shortName": "X"}})
    assert res.passed and res.score == 5.0


def test_news_rejects_red_flag(monkeypatch):
    monkeypatch.setattr(llm_client, "call_deepseek",
                        lambda *a, **k: json.dumps({"sentiment": "neutral",
                                                    "imminence": "coming",
                                                    "red_flags": ["fraud"]}))
    data = {"headlines": [{"title": "h"}], "info": {"shortName": "X"}}
    res = g8_news_catalyst.check("X", data)
    assert not res.passed and "fraud" in res.reasoning


def test_news_pass_positive_coming(monkeypatch):
    monkeypatch.setattr(llm_client, "call_deepseek",
                        lambda *a, **k: json.dumps({"sentiment": "positive",
                                                    "catalyst_type": "product",
                                                    "imminence": "coming",
                                                    "red_flags": []}))
    data = {"headlines": [{"title": "h"}], "info": {"shortName": "X"}}
    res = g8_news_catalyst.check("X", data)
    assert res.passed and res.score > 5


# ---- Gate 8.3 propagation ----

def test_propagation_adds_read_through():
    added = g8_3_propagation.propagate([("NVDA", "product_launch")])
    assert "AMD" in added and "MU" in added


# ---- Gate 8.5 sentiment ----

def test_sentiment_flags_euphoria():
    closes = np.concatenate([np.full(40, 50.0), np.linspace(50, 75, 21)])  # parabolic
    vols = np.concatenate([np.full(56, 1e6), np.full(5, 5e6)])
    res = g8_5_sentiment.check("X", {"bars": _frame(closes, vols)})
    assert res.passed  # never hard-rejects
    assert res.score < 5  # conviction reduced


def test_sentiment_calm_neutral():
    closes = 50 + np.sin(np.linspace(0, 6, 80))
    res = g8_5_sentiment.check("X", {"bars": _frame(closes)})
    assert res.score == 5.0


# ---- V2 debate stage ----

def test_llm_stage_uses_debate(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    from engine import funnel
    survivors = [{"ticker": "NVDA", "total": 50.0, "sector": "Tech",
                  "catalyst": {"type": "earnings", "date": "2026-08-10",
                               "days_out": 35},
                  "scores": {"g2_trend": 8.0}, "reasonings": {},
                  "vote": 8.0, "_data": {}}]
    out = funnel.run_llm_stage(survivors, top=1, with_propagation=False,
                               verbose=False)
    f = out["finalists"][0]
    assert "debate" in f and "veteran" not in f
    assert f["debate"]["verdict"] == "take"
    # mock judge: conviction 7 >= 6 and p 0.44 >= 0.35 and mock news passes
    assert f["llm_passed"] is True
