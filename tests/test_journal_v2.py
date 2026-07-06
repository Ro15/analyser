from journal import dashboard, tracker


def _plan(ticker="NVDA"):
    return {"ticker": ticker, "entry_zone": [95.0, 102.0], "reference_price": 100.0,
            "target": 120.0, "time_stop": "2026-10-01", "catalyst": None}


def test_log_alert_v2_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    rec = tracker.log_alert(_plan(), scores={"g2_trend": 8.0}, conviction=7,
                            probability=0.44, pipeline_version=2, size="half",
                            kill_condition="catalyst cancelled",
                            debate={"verdict": "take", "reasoning": "x"})
    assert rec["pipeline_version"] == 2
    assert rec["size"] == "half"
    assert rec["p_target_90d"] == 0.44
    assert rec["kill_condition"] == "catalyst cancelled"
    assert rec["debate"]["verdict"] == "take"
    assert rec["postmortem_done"] is False


def test_set_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    rec = tracker.log_alert(_plan("AMD"), pipeline_version=2)
    tracker.set_fields(rec["id"], postmortem_done=True)
    assert tracker.all_alerts()[0]["postmortem_done"] is True


def test_dashboard_version_filter():
    records = [
        {"ticker": "A", "status": "closed", "issued": "2026-06-01",
         "resolved_on": "2026-06-20", "realized_return": 0.2,
         "reference_price": 100.0, "entry_zone": [95.0, 102.0]},
        {"ticker": "B", "status": "closed", "issued": "2026-06-01",
         "resolved_on": "2026-06-20", "realized_return": -0.1,
         "reference_price": 100.0, "entry_zone": [95.0, 102.0],
         "pipeline_version": 2},
    ]
    all_ = dashboard.build(records)
    v1 = dashboard.build(records, pipeline_version=1)
    v2 = dashboard.build(records, pipeline_version=2)
    assert all_["n_closed"] == 2
    assert v1["n_closed"] == 1 and v1["win_rate"] == 1.0
    assert v2["n_closed"] == 1 and v2["win_rate"] == 0.0
