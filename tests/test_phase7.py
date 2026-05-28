import datetime as dt

from engine import broker, structuring
from journal import dashboard
from tests.conftest import _frame
import numpy as np


def _data(seed=0):
    rng = np.random.default_rng(seed)
    return {"bars": _frame(np.abs(50 + np.cumsum(rng.normal(0.1, 1, 200))) + 10)}


def test_broker_paper_endpoint_only():
    assert "paper" in broker.PAPER_BASE
    broker._assert_paper(broker.PAPER_BASE)  # must not raise


def test_broker_simulates_without_keys(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET", raising=False)
    plan = structuring.build_plan("NVDA", _data(1))
    order = broker.place_paper_entry(plan)
    assert order["simulated"] is True
    assert order["ticker"] == "NVDA"


def test_dashboard_metrics(monkeypatch):
    records = [
        {"ticker": "A", "status": "closed", "issued": "2026-01-02",
         "resolved_on": "2026-03-02", "reference_price": 100, "entry_zone": [93, 101],
         "target": 115, "realized_return": 0.18},
        {"ticker": "B", "status": "closed", "issued": "2026-01-10",
         "resolved_on": "2026-03-10", "reference_price": 50, "entry_zone": [47, 51],
         "target": 57.5, "realized_return": -0.04},
        {"ticker": "C", "status": "open", "issued": "2026-05-01",
         "reference_price": 20, "entry_zone": [19, 21], "target": 23,
         "realized_return": None},
    ]
    monkeypatch.setattr(dashboard.tracker, "all_alerts", lambda: records)
    monkeypatch.setattr(dashboard, "_spy_return", lambda s, e: 0.05)  # no network

    d = dashboard.build()
    assert d["n_closed"] == 2 and d["n_open"] == 1
    assert d["open_positions"] == ["C"]
    assert d["win_rate"] == 0.5
    # cum = 1.18*0.96 - 1 = 0.1328 ; spy_cum = 1.05^2 - 1 = 0.1025
    assert round(d["cum_return"], 4) == 0.1328
    assert round(d["excess_vs_spy"], 4) == round(0.1328 - 0.1025, 4)
    assert d["avg_R"] != 0.0
