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


def test_effective_weights_merges_learned_over_defaults(tmp_path, monkeypatch):
    """Three tiers: learned beats default beats 1.0 fallback."""
    from journal import tuner

    learned_path = tmp_path / "weights.json"
    learned_path.write_text('{"g2_trend": 1.4}')
    monkeypatch.setattr(tuner, "_PATH", str(learned_path))

    defaults = {"g2_trend": 1.2, "g3_sector": 0.9}
    merged = tuner.effective_weights(defaults)
    assert merged["g2_trend"] == 1.4   # learned overrides default
    assert merged["g3_sector"] == 0.9  # default kept where no learning
    assert merged.get("g5.3_priced_in") is None  # caller falls back to 1.0


def test_compute_vote_weighted_mean():
    """Weighted mean over voters; missing labels skipped; empty -> 0."""
    from engine import voting
    scores = {"g2_trend": 8.0, "g3_sector": 6.0, "g4_rel_strength": 10.0}
    weights = {"g2_trend": 1.2, "g3_sector": 0.8, "g4_rel_strength": 2.0}
    voters = ["g2_trend", "g3_sector", "g4_rel_strength"]
    expected = (1.2 * 8.0 + 0.8 * 6.0 + 2.0 * 10.0) / (1.2 + 0.8 + 2.0)
    assert abs(voting.compute_vote(scores, voters, weights) - expected) < 1e-9

    # Missing voter labels are skipped silently.
    assert voting.compute_vote({"g2_trend": 5.0}, ["g2_trend", "g3_sector"],
                                {"g2_trend": 1.0, "g3_sector": 1.0}) == 5.0

    # Missing weight defaults to 1.0.
    assert voting.compute_vote({"g2_trend": 5.0}, ["g2_trend"], {}) == 5.0

    # No voters present -> 0.0.
    assert voting.compute_vote({}, [], {}) == 0.0


def test_effective_weights_no_file_returns_defaults(tmp_path, monkeypatch):
    from journal import tuner
    monkeypatch.setattr(tuner, "_PATH", str(tmp_path / "missing.json"))
    assert tuner.effective_weights({"g2_trend": 1.2}) == {"g2_trend": 1.2}
    assert tuner.effective_weights({}) == {}
    assert tuner.effective_weights(None) == {}


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
