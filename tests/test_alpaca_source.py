"""Unit tests for the Alpaca universe filter (pure logic, no network)."""
import os
import time

from data.ingest import alpaca_source as src


def _asset(symbol="AAPL", name="Apple Inc", exchange="NASDAQ", tradable=True):
    return {"symbol": symbol, "name": name, "exchange": exchange,
            "tradable": tradable, "class": "us_equity", "status": "active"}


def test_keeps_common_stock_on_primary_venue():
    assert src.is_common_stock(_asset("AAPL", "Apple Inc", "NASDAQ"))
    assert src.is_common_stock(_asset("JPM", "JPMorgan Chase & Co", "NYSE"))


def test_drops_non_tradable():
    assert not src.is_common_stock(_asset(tradable=False))


def test_drops_secondary_venues():
    assert not src.is_common_stock(_asset("XYZ", "Some ETF Issuer", "ARCA"))
    assert not src.is_common_stock(_asset("ABC", "Penny Co", "OTC"))
    assert not src.is_common_stock(_asset("DEF", "Whatever", "BATS"))


def test_drops_funds_by_name():
    assert not src.is_common_stock(_asset("SPY", "SPDR S&P 500 ETF Trust", "NYSE"))
    assert not src.is_common_stock(_asset("QQQ", "Invesco QQQ Trust", "NASDAQ"))
    assert not src.is_common_stock(_asset("IWM", "iShares Russell 2000 ETF", "NYSE"))


def test_avg_dollar_volume():
    bars = [{"c": 10.0, "v": 100}, {"c": 20.0, "v": 100}]
    assert src.avg_dollar_volume(bars) == (1000 + 2000) / 2
    assert src.avg_dollar_volume([]) == 0.0


def test_get_universe_uses_fresh_cache(tmp_path, monkeypatch):
    """A recent cache is reused; build() is NOT called (no network)."""
    import json
    from data.ingest import universe as U

    monkeypatch.setattr(U, "_CACHE", str(tmp_path))
    cache = tmp_path / "universe.json"
    cache.write_text(json.dumps(["AAPL", "MSFT"]))

    def _boom(*a, **k):
        raise AssertionError("build() should not run when cache is fresh")

    monkeypatch.setattr(U, "build", _boom)
    assert U.get_universe(max_age_days=7) == ["AAPL", "MSFT"]


def test_get_universe_rebuilds_when_stale(tmp_path, monkeypatch):
    """A missing/old cache triggers a rebuild via build()."""
    from data.ingest import universe as U

    monkeypatch.setattr(U, "_CACHE", str(tmp_path))
    monkeypatch.setattr(U, "build", lambda **k: [{"ticker": "NVDA"}])
    monkeypatch.setattr(U, "save", lambda rows, path=None: None)
    assert U.get_universe(max_age_days=7) == ["NVDA"]


def test_cache_freshness_rule(tmp_path):
    """Stale files refresh when max_age_hours is set; never expire when None."""
    from backtest import data_cache

    f = tmp_path / "x.parquet"
    f.write_text("x")
    # backtest mode: None -> always considered fresh (permanent cache)
    assert data_cache._is_fresh(str(f), None) is True
    # live mode: a brand-new file is fresh
    assert data_cache._is_fresh(str(f), 18) is True
    # make it look 20 hours old -> stale under an 18h rule
    old = time.time() - 20 * 3600
    os.utime(str(f), (old, old))
    assert data_cache._is_fresh(str(f), 18) is False
    assert data_cache._is_fresh(str(f), None) is True


def test_sector_name_translation():
    """Screener sector names map to the GICS names the sector gates expect."""
    from engine import sectors

    assert sectors.to_gics("Health Care") == "Healthcare"
    assert sectors.to_gics("Finance") == "Financial Services"
    assert sectors.to_gics("Telecommunications") == "Communication Services"
    assert sectors.to_gics("Technology") == "Technology"   # already GICS
    assert sectors.to_gics("Miscellaneous") is None         # no clean mapping
    assert sectors.to_gics("") is None
    # every mapped value must be a real GICS sector with an ETF
    for gics in sectors.NASDAQ_SECTOR_TO_GICS.values():
        assert gics in sectors.SECTOR_ETF
