# V2 Upgrade: Richer Data + Debate Brain + Exit Reviews

**Date:** 2026-07-06
**Status:** Approved by user (design walkthrough, 4 parts)
**Goal:** Every market night, send one Telegram digest. When the bot names a stock as a buy alert, it must have a genuine shot at **+20% within 90 days**. Improve entry quality, winner size, and exits together. Paper trading only.

## Context and decisions made

- Current bot: gate-funnel swing bot at `/Users/ro/analyser` (see CLAUDE.md). 4 weeks of nightly runs, 47 journaled paper trades (13 closed winners, 34 open of which 27 underwater at design time). Weakness: no re-examination of open positions, single-opinion LLM review, blind to short/options/insider data.
- Two reference projects were evaluated in `/Users/ro/Desktop/analyser/hedge`:
  - **OpenBB** → adopted as a *data library*, contained behind one module.
  - **TradingAgents** → its bull/bear/judge *pattern* is rebuilt natively on the existing `engine/llm_client.py`. The framework itself is NOT a dependency (own data fetching, no cost-cap/LLM_MOCK integration).
  - Hermes-agent → explicitly excluded.
- Approach chosen (user picked 1 of 3): "their strengths, our engine." No from-scratch rewrite; the orchestration layer (`scan.py`, alert formatting) is rebuilt, everything else evolves in place. The existing journal history is preserved; all new entries carry `pipeline_version: 2`.
- Budget: existing `monthly_cost_cap_usd: 20.0` unchanged. Expected spend $2–5/month (DeepSeek for bulk roles, Claude for the judge). June 2026 actual spend was ~$0.30.
- Target changes from +15% to **+20%**; hold window stays 60–90 days; scale-out level moves to +20%. Target must be a `config.yaml` tunable so the backtest can compare 15 vs 20.

## Part 1 — Data layer (OpenBB) and gate changes

Install `openbb` into the analyser venv. All access goes through **one new module** `data/ingest/openbb_source.py`; nothing else imports openbb. Every fetch is keyless/free, cached under `.cache/` (parquet/JSON, same pattern as prices), and returns `None` on any failure so gates degrade to a neutral pass.

Signals (all verified working keyless on 2026-07-06):

1. **Daily short / dark-pool volume** — provider `stockgrid`. Trend of short-volume % over ~10 sessions.
2. **Short interest + days-to-cover** — provider `finra` (`obb.equity.shorts.short_interest`). Twice-monthly settlement data; slow signal, acceptable for 60–90 day holds.
3. **Options flow snapshot** — provider `yfinance` chains: put/call volume and OI ratio, unusual call-volume vs its own average, near-dated IV.
4. **Options expected move** — from the chain: straddle price at the expiry just after the catalyst date implies the market's expected % move. Compare with our +20% thesis.
5. **Insider transactions** — provider `sec` (`obb.equity.ownership.insider_trading`): officer/director buys vs sells in the last ~60 days.
6. **Analyst consensus** — provider `yfinance` (`obb.equity.estimates.consensus`): target vs price, recommendation mean. NOT a gate — passed as context to the debate.

Gate changes (2 new, 2 upgraded — no gate sprawl):

- **NEW `gates/g6_7_short_pressure.py`** — combines (1) short-volume trend and (2) short interest/days-to-cover. Rising short pressure into entry = penalty; drying up = bonus; high short interest **plus** strong fundamentals/catalyst = explicit squeeze-fuel bonus (serves the +20% goal).
- **NEW `gates/g6_8_options_flow.py`** — signal (3). Unusual call buying = bonus; heavy put buying = penalty; no meaningful options market = neutral pass (do not punish small caps).
- **UPGRADED `gates/g5_3_priced_in.py`** — adds signal (4): if options already price a move ≥ our target, the catalyst is priced in → penalty; if the implied move is far below our thesis, edge confirmed → bonus. Keeps existing price-action heuristics.
- **UPGRADED `gates/g6_5_smart_money.py`** — adds signal (5): recent insider buying = strong bonus, heavy selling = penalty, on top of existing checks.

Both new gates sit late in `CHAIN` (per-ticker network fetches → survivors only). All thresholds/weights in `config.yaml`. Standard gate contract, rejections logged with reasons, one unit test each on synthetic fixtures.

## Part 2 — Debate stage (replaces single veteran review, gate 9)

New `engine/debate.py`, run only on `max_finalists` survivors. Existing LLM gates 8 (news), 8.3 (propagation), 8.5 (sentiment) are unchanged; the debate replaces only gate 9 (veteran review):

1. **Bull** (DeepSeek): strongest honest case FOR +20% in 90 days. Input: gate scores, news, catalyst, short/options/insider data, analyst consensus.
2. **Bear** (DeepSeek): strongest case AGAINST — what kills it, what's priced in.
3. **Judge** (Claude, one call): reads both + the lessons playbook (Part 4). Returns structured JSON: `verdict` (take/pass), `p20_90d` (probability of +20% in 90 days), `conviction` (1–10), `size` (full/half/pass), `kill_condition` (concrete observable that invalidates the thesis), `reasoning`.

Plumbing: existing `llm_client` only — hard monthly cap, `LLM_MOCK=1` returns deterministic canned JSON for all three roles, missing key = neutral pass. ~3 calls/finalist. Full bull/bear/judge record is stored on the journal entry. The judge's `kill_condition` feeds Part 3.

## Part 3 — Nightly exit re-check of open positions

New `journal/position_review.py`, invoked by `scan.py` after the main funnel:

1. **Deterministic red-flag screen (no LLM, every open position):** catalyst date passed without resolution; short-volume spike in the name; decisive trend break (e.g., close below 50DMA by a config threshold); sector/regime turn; original `kill_condition` observed. Each flag = 1 point; thresholds in `config.yaml`.
2. **Judge review (only positions with ≥2 flags):** "entry thesis was X, here is what changed — is the thesis dead?" If dead → **EXIT EARLY** Telegram item + journal closes the position as `resolution: "thesis_broken"` at that night's price with realized return.

Guardrail preserved: exits remain thesis/catalyst-based, never a bare price stop — price deterioration is one flag among several, never sufficient alone.

## Part 4 — Learning loop, digest, sizing

- **Post-mortems:** on every trade close (any resolution), one cheap LLM call writes a short lesson: which scores misled, what the bear got right, what to weigh differently. Appended to `.state/playbook.md` (rolling, size-capped; oldest lessons summarized/compacted when over the cap). The judge receives this file in every debate. The numeric tuner (`journal/tuner.py`) is unchanged and continues independently (two learning channels: words and numbers).
- **Conviction-weighted alerts:** judge `size` (full/half) appears in the alert. Existing portfolio filters (g9.5 correlation, sector caps) unchanged.
- **Nightly digest (rebuilt `alerts/` formatting):** exactly one Telegram message per market night: 🟢 buy alerts with size (only when the +20% bar is cleared), 👀 top-3 near-misses labeled "watchlist — not buy signals", 🏥 exit-early items, one-line portfolio pulse (open count, P&L vs SPY). No silent nights; no low-conviction padding as buys.

## Orchestration rebuild

`scan.py` is restructured into the v2 nightly flow: funnel → debate → correlation/structuring → journal → position review → post-mortems → digest. Journal schema additions: `pipeline_version: 2`, `debate` record, `kill_condition`, `size`, `p20_90d`; new resolution value `thesis_broken`. Old v1 entries remain valid and readable; `journal/dashboard.py` reports v1 vs v2 separately.

## Error handling

- Any OpenBB/provider failure → signal `None` → gate neutral pass; scan never dies on a data source.
- LLM failure or cap reached → existing graceful degradation (neutral pass; no alert fires from a failed judge — a finalist without a judge verdict goes to the watchlist, not to buys).
- Telegram failure → existing dry-run/log fallback.
- Position review failure → log and skip; never blocks the main scan or the digest.

## Testing & validation

- Full suite runs offline: `LLM_MOCK=1`, synthetic OHLCV fixtures; new fixtures for short volume, options chains, insider data. One unit test per new/changed gate, plus tests for debate JSON parsing, red-flag screen, position-review close path, playbook compaction, digest assembly.
- Live-data assertions use existing `maybe_live` (self-skip on network failure).
- Backtest: deterministic new gates (short pressure from FINRA history where obtainable) added to the sweep; **options and daily short-volume signals have no free history** → validated in paper trading only, and `backtest/report.py` must print that limitation alongside the existing survivorship-bias warning.
- Go-live rule unchanged: no real capital unless v2 beats SPY on paper over the full window.

## Rollout (stage by stage, tested live at each step)

1. Build + unit tests offline (`LLM_MOCK=1`).
2. Full mock dry-run of the whole nightly flow.
3. One or more live **shadow nights**: v2 runs and logs; v1 picks also logged for comparison; digest marked "shadow".
4. Cutover: v2 becomes the launchd nightly. `run_nightly.sh` unchanged.

## Guardrails (restated, never removed)

- Paper trading only; go-live requires beating SPY over the full paper window.
- Gate 5.5 valuation ceiling stays.
- Catalyst-invalidation exits, never a bare price stop.
- No hardcoded/committed API keys; secrets via `.env`.
- Hard monthly LLM cost cap enforced in code.
