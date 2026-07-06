"""Gate 6.7 -- short pressure (V2, finalist stage).

Reads enrichment injected by engine/enrichment.py:
  data["short_volume"]   {"short_pct": [...]}    stockgrid daily short volume %
  data["short_interest"] {"days_to_cover": ...}  FINRA twice-monthly
  data["gate_scores"]    main-chain scores (for the squeeze-fuel bonus)

Rising short-selling into our entry = penalty; drying up = bonus; heavy short
interest on a fundamentally strong name = squeeze fuel (+20% goal helper).
Voter gate: never hard-rejects; missing data -> neutral 5.
"""
from engine.config import load_config
from engine.types import GateResult


def check(ticker, data):
    cfg = load_config().get("short_pressure", {})
    sessions = int(cfg.get("trend_sessions", 10))
    delta = float(cfg.get("trend_delta", 0.10))
    dtc_min = float(cfg.get("dtc_squeeze_min", 5.0))
    fund_min = float(cfg.get("squeeze_fund_min", 7.0))

    pcts = ((data.get("short_volume") or {}).get("short_pct") or [])[-sessions:]
    si = data.get("short_interest") or {}

    score, notes = 5.0, []
    if len(pcts) >= 6:
        recent = sum(pcts[-3:]) / 3
        base = sum(pcts[:-3]) / len(pcts[:-3])
        change = (recent / base - 1) if base > 0 else 0.0
        if change >= delta:
            score -= 3.0
            notes.append(f"short volume rising ({change:+.0%} vs base)")
        elif change <= -delta:
            score += 2.0
            notes.append(f"short volume drying up ({change:+.0%})")
        else:
            notes.append("short volume flat")
    else:
        notes.append("no daily short-volume data")

    dtc = si.get("days_to_cover")
    if isinstance(dtc, (int, float)):
        notes.append(f"days-to-cover {dtc:.1f}")
        fund = (data.get("gate_scores") or {}).get("g5.7_fundamentals", 0)
        if dtc >= dtc_min and fund >= fund_min:
            score += 2.0
            notes.append("high short interest + strong fundamentals -> squeeze fuel")
    else:
        notes.append("no FINRA short interest")

    score = round(max(0.0, min(10.0, score)), 2)
    return GateResult(True, score, f"Short pressure: {'; '.join(notes)}.")
