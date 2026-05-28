# Catalyst Anticipation Swing Bot

## Goal
Find US stocks likely to rise 15%+ in 60-90 days because a catalyst is COMING (not yet priced in), confirmed by fundamentals, flow, and smart money. Filter out overvalued tops and accounting traps.

## Trading Style
- Entry: buy on alert, ahead of an anticipated catalyst
- Hold: 60-90 days
- Target: +15% (partial scale-out)
- Exit: catalyst-invalidation logic (NOT a hard price stop) + time stop at catalyst date + buffer
- PAPER TRADING ONLY for the first 6 months (Alpaca paper account)

## Architecture
20-gate funnel: ~3,000 stocks -> 3-4 Telegram alerts/night. Cheap deterministic filters first (pure Python/SQL); LLM only on the final ~16 stocks. Each gate is its own module in gates/ and returns GateResult(passed: bool, score: float, reasoning: str).

## Build Order (follow strictly, do not skip ahead)
1. Skeleton + data layer + core gates (0,1,2,5) + analyze.py
2. Backtest harness on core gates -- PROVE EDGE vs SPY before building more
3. Full funnel (add gates 2.5,3,4,5.3,5.5,5.7,6,6.5,7,7.5)
4. Catalyst calendar + "already priced in" detector
5. LLM gates (8 news via DeepSeek, 8.3 propagation, 9 veteran review via Claude)
6. Telegram alerts + journal/post-mortem learning loop (gate 12)
7. Paper trade 6 months, measure vs SPY

## Tech Stack
- Python 3.11+, PostgreSQL on port 5432 (use a SEPARATE database from any existing trading bot)
- Data: yfinance (free, no key, primary), Alpaca (paper), SEC EDGAR (insider/13F), NewsAPI (free tier)
- LLM: DeepSeek (cheap, news), Claude (veteran review)
- Alerts: Telegram (a NEW bot, separate from any existing one)

## Guardrails (never remove)
- Gate 5.5 valuation ceiling: reject names in the top decile of their own 5-year valuation range (anti-FOMO)
- Gate 10 catalyst-invalidation exit: always define a concrete way out
- Backtest must beat SPY after costs before going live
- NEVER hardcode or commit API keys. All secrets come from .env via environment variables.

## Known Data Caveat
yfinance gives CURRENT index membership, not point-in-time, so backtests have SURVIVORSHIP BIAS and will look better than reality. The backtest report MUST print a warning stating results are optimistic for this reason.

## Conventions
- Each gate: gates/gN_name.py with function check(ticker, data) -> GateResult
- GateResult is a namedtuple: (passed, score, reasoning)
- Log every rejection with its reason
- One unit test per gate in tests/
