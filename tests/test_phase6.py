import datetime as dt

import numpy as np

from alerts import formatter, telegram_bot
from engine import structuring
from gates import g9_5_correlation
from journal import review, tracker, tuner
from tests.conftest import _frame


def _data(seed=0):
    rng = np.random.default_rng(seed)
    closes = 50 + np.cumsum(rng.normal(0.1, 1, 200))
    return {"bars": _frame(np.abs(closes) + 10)}


# ---- structuring (gate 10) ----

def test_build_plan_has_invalidation_and_timestop():
    cat = {"type": "product_launch", "date": dt.date(2026, 6, 25),
           "days_out": 28, "description": "launch"}
    plan = structuring.build_plan("NVDA", _data(1), catalyst=cat, conviction=4)
    assert plan["entry_zone"][0] <= plan["reference_price"] <= plan["entry_zone"][1] + 1
    assert plan["target"] > plan["reference_price"]
    assert any("cancelled" in s for s in plan["invalidation_exit"])  # guardrail present
    assert plan["time_stop"] == str(dt.date(2026, 6, 25) + dt.timedelta(days=10))


def test_build_plan_time_stop_without_catalyst():
    plan = structuring.build_plan("X", _data(2), catalyst=None)
    assert plan["catalyst"] is None
    assert plan["time_stop"] > dt.date.today().isoformat()


# ---- correlation / concentration (gate 9.5) ----

def test_sector_cap():
    cands = [{"ticker": f"T{i}", "sector": "Tech", "total": 100 - i, "_data": _data(i)}
             for i in range(4)]
    kept, dropped = g9_5_correlation.filter_candidates(cands, max_per_sector=2)
    assert len(kept) == 2
    assert all("sector cap" in d["drop_reason"] for d in dropped)


def test_correlation_drop():
    shared = _data(7)
    cands = [
        {"ticker": "A", "sector": "Tech", "total": 100, "_data": shared},
        {"ticker": "B", "sector": "Energy", "total": 90, "_data": shared},  # identical -> corr 1
    ]
    kept, dropped = g9_5_correlation.filter_candidates(cands, corr_max=0.7)
    assert len(kept) == 1 and len(dropped) == 1
    assert "corr" in dropped[0]["drop_reason"]


# ---- alerts ----

def test_formatter_contains_fields():
    plan = structuring.build_plan("NVDA", _data(3),
                                  catalyst={"type": "pdufa", "date": "2026-07-01",
                                            "days_out": 34, "description": "x"},
                                  conviction=4, probability=0.4)
    msg = formatter.format_alert(plan, news="positive", veteran="approve",
                                 read_through=["AMD", "MU"])
    assert "NVDA" in msg and "Entry zone" in msg and "Invalidation" in msg
    assert "AMD" in msg


def test_telegram_dry_run():
    res = telegram_bot.send("hello", dry_run=True)
    assert res["ok"] and res["dry_run"]


# ---- journal (gate 12) ----

def test_journal_log_resolve_review_tune(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    monkeypatch.setattr(tuner, "_PATH", str(tmp_path / "w.json"))

    for i in range(25):
        plan = structuring.build_plan(f"T{i}", _data(i))
        rec = tracker.log_alert(plan, setup="breakout", sector="Tech",
                                conviction=4, scores={"g5_setups": 8.0 + (i % 3)},
                                today=dt.date(2026, 1, 1))
        win = i % 2 == 0
        tracker.resolve(rec["id"], resolution="hit_target" if win else "time_stop",
                        realized_return=0.18 if win else -0.05)

    b = review.breakdown()
    assert b["n_closed"] == 25
    assert "breakout" in b["by_setup"]

    out = tuner.tune()
    assert out["status"] == "tuned"
    assert all(0.5 <= w <= 1.5 for w in out["weights"].values())


def test_journal_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    plan = structuring.build_plan("DUP", _data(1))
    tracker.log_alert(plan, today=dt.date(2026, 1, 1))
    tracker.log_alert(plan, today=dt.date(2026, 1, 1))
    assert len([r for r in tracker.all_alerts() if r["ticker"] == "DUP"]) == 1
