from alerts import digest


def _finalist(ticker, conviction=7):
    return {"ticker": ticker,
            "debate": {"verdict": "take", "conviction": conviction,
                       "p_target_90d": 0.44, "size": "half",
                       "reasoning": "bear case priced in"}}


def test_digest_no_buys_still_a_message(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNAL_PATH", str(tmp_path / "j.jsonl"))
    msg = digest.build_digest([], [], [], digest.portfolio_pulse())
    assert "Nightly digest" in msg
    assert "none cleared the +20% bar" in msg
    assert "no positions yet" in msg


def test_digest_sections_render():
    exits = [{"ticker": "ADTN", "return": -0.25, "reason": "catalyst dead",
              "flags": ["trend break"]}]
    msg = digest.build_digest([_finalist("NVDA")],
                              [_finalist("AMD"), _finalist("MU")],
                              exits, "3 open avg -1.0%")
    assert "NVDA" in msg and "HALF" in msg and "7/10" in msg
    assert "Watchlist" in msg and "NOT buy signals" in msg and "AMD" in msg
    assert "Exit early" in msg and "ADTN" in msg and "-25.0%" in msg
    assert "3 open avg -1.0%" in msg


def test_watchlist_capped_at_config():
    watch = [_finalist(f"T{i}") for i in range(6)]
    msg = digest.build_digest([], watch, [], "x")
    assert msg.count("• T") == 3        # digest.watchlist_size


def test_shadow_marker():
    msg = digest.build_digest([], [], [], "x", shadow=True)
    assert "[SHADOW]" in msg
