# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is
Catalyst Anticipation Swing Bot: find US stocks likely to rise 15%+ in 60-90 days because a catalyst is COMING (not yet priced in), confirmed by fundamentals, flow, and smart money; filter out overvalued tops and accounting traps. Entry on alert, hold 60-90 days, scale out at +15%, exit via catalyst-invalidation (NOT a hard price stop) + time stop at catalyst date + buffer. PAPER TRADING ONLY for the first 6 months.

## Commands
Setup (Python 3.11+; a venv already lives in `venv/`):
```
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill in keys; none required for the keyless dry-run path
```
Run everything through the venv interpreter (`./venv/bin/python ...`):
```
./venv/bin/python -m pytest -q                      # full suite (synthetic fixtures; live-data tests self-skip)
./venv/bin/python -m pytest tests/test_g2_trend.py  # one test file
./venv/bin/python -m pytest -k valuation            # tests matching a keyword
./venv/bin/python analyze.py NVDA                   # single-stock Phase-1 report (gates 0,1,2,5)
LLM_MOCK=1 ./venv/bin/python scan.py --universe 40  # full nightly pipeline, no keys/network for LLM, Telegram dry-run
./venv/bin/python scan.py --live                    # real run; sends Telegram only if TELEGRAM_* set
./venv/bin/python -m backtest.harness               # replay core gates vs SPY (prints optimism warning)
./venv/bin/python -m journal.dashboard              # paper P&L vs SPY
./venv/bin/python -m journal.tuner                  # nudge gate weights from realized returns
```
Tests/modules import as top-level packages, so always run from the repo root. There is no linter/formatter configured. Postgres is OPTIONAL — the live pipeline runs on yfinance + a parquet cache; `data/store.py` is only used if a DB is reachable.

## Architecture (the big picture)
Three entry points sit on top of one shared gate library: `analyze.py` (single stock), `scan.py` (nightly end-to-end), `backtest/harness.py` (edge validation).

**The funnel is the spine** (`engine/funnel.py`). A `CHAIN` list defines gate order cheap->expensive; cheap deterministic filters run on ~thousands of names, expensive fundamental/LLM gates only on the few that survive.
- Gate 0 (regime, `g0_regime`) is SYSTEM-level: if it fails, the whole night is a no-go and zero alerts fire.
- Per ticker the funnel walks `CHAIN`, breaks at the FIRST failed gate, and logs the rejection reason. Survivors get a catalyst boost, are sorted by total score, and the top N go to the LLM stage.
- Gate numbering uses decimals (`g2_5`, `g5_3`, `g5_5`...) to mark insertion order between the original integer gates. **Funnel order is the `CHAIN`/`run_llm_stage` sequence, NOT filename sort order.**

**Gate contract** (`engine/types.py`): every gate is `gates/gN_name.py` exposing `check(ticker, data) -> GateResult(passed, score, reasoning)` (a namedtuple). The `data` dict is shared context assembled once in `funnel._prefetch_context` (market/VIX/SPX, sector ETF bars, macro tickers, `rs_universe_returns`) plus per-ticker fields (`bars`, `info`, `sector`). Gates are declarative — all thresholds live in `config.yaml` so the backtest can sweep them.

**LLM stage** (`funnel.run_llm_stage`, runs only on `max_finalists`): gate 8 news (DeepSeek), 8.5 sentiment, 8.3 propagation/read-through, 9 veteran review (Claude). `engine/llm_client.py` reads keys from `.env`, enforces a HARD monthly $ cap (`.state/llm_cost.json`), and degrades gracefully: no key -> neutral pass, or set `LLM_MOCK=1` for deterministic canned JSON so the whole pipeline runs offline.

**After the LLM stage** (`scan.py`): gate 9.5 correlation/concentration filter -> gate 10 structuring (`engine/structuring.py`: entry zone, +15% target with scale-out, catalyst-invalidation exit, time stop) -> `journal/tracker.log_alert` -> `alerts/formatter` -> `alerts/telegram_bot` (dry-run unless `TELEGRAM_*` configured).

**Data layer**: `backtest/data_cache.py` fetches each ticker's history once via `data/ingest/prices.py` (yfinance) and caches in-memory + `.cache/*.parquet`. `data/store.py` is the optional Postgres OHLCV store, guarded by `is_available()` so tests and the live path skip cleanly without a DB.

**Learning loop**: `journal/tracker.py` persists alerts and their realized returns; `journal/tuner.py` nudges per-gate weights into `.state/gate_weights.json` from the correlation between a gate's score and realized return (needs >=20 closed trades, clamped to [0.5, 1.5]); `journal/dashboard.py` compares paper P&L against buying SPY on the same dates.

**Backtest discipline** (`backtest/harness.py`): no look-ahead is ASSERTED at runtime (gates on date t see only bars <= t; forward returns use bars strictly after t). The universe is current index membership, so results carry SURVIVORSHIP BIAS — the report MUST print that warning.

State/cache dirs are gitignored: `.cache/` (parquet bars), `.state/` (`llm_cost.json`, `gate_weights.json`), and the journal store.

## Guardrails (never remove)
- Gate 5.5 valuation ceiling: reject names in the top decile of their own ~5-year valuation range (anti-FOMO).
- Gate 10 catalyst-invalidation exit: always define a concrete way out.
- Backtest must beat SPY after costs before going live; do not move to real capital until paper results beat SPY over the full 6-month window.
- NEVER hardcode or commit API keys. All secrets come from `.env` via environment variables.

## Conventions
- One gate per file `gates/gN_name.py` with `check(ticker, data) -> GateResult`; log every rejection with its reason.
- One unit test per gate in `tests/`, driven by synthetic OHLCV fixtures in `tests/conftest.py` (live-data assertions use `maybe_live`, which skips on network/rate-limit failure).
- Add new tunables to `config.yaml`, not inline constants, so the backtest can sweep them.
