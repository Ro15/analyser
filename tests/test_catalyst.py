import datetime as dt

from catalyst import calendar_db, relationship_map


def _no_earnings(monkeypatch):
    # Isolate seed events from live yfinance earnings in tests.
    monkeypatch.setattr(calendar_db, "_earnings_events", lambda t: [])


def test_seed_catalyst_in_ideal_window(monkeypatch):
    _no_earnings(monkeypatch)
    today = dt.date(2026, 5, 28)
    cat = calendar_db.best_in_window("NVDA", hold_days=90, today=today)
    assert cat is not None
    assert cat["type"] == "product_launch"
    assert cat["days_out"] == 28          # 2026-06-25 - 2026-05-28
    assert cat["boost"] == 5.0            # 14..56d ideal window


def test_no_catalyst_returns_none(monkeypatch):
    _no_earnings(monkeypatch)
    cat = calendar_db.best_in_window("MMM", hold_days=90, today=dt.date(2026, 5, 28))
    assert cat is None


def test_upcoming_filters_window(monkeypatch):
    _no_earnings(monkeypatch)
    today = dt.date(2026, 5, 28)
    assert len(calendar_db.upcoming("NVDA", within_days=90, today=today)) == 1
    assert len(calendar_db.upcoming("NVDA", within_days=10, today=today)) == 0


def test_relationship_read_through():
    rt = relationship_map.read_through("NVDA")
    assert "AMD" in rt and "MU" in rt and "AVGO" in rt


def test_relationship_is_bidirectional():
    # TSM is a supplier to NVDA -> NVDA should be a customer of TSM.
    rels = dict(relationship_map.related("TSM"))
    assert rels.get("NVDA") == "customer"


def test_add_edge_extends_graph():
    relationship_map.add_edge("FOO", "BAR", "competitor")
    assert "BAR" in relationship_map.read_through("FOO")
    assert "FOO" in relationship_map.read_through("BAR")
