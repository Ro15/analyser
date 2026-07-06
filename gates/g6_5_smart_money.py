"""Gate 6.5 -- smart money (insider / institutional). V2.

BOOST on an insider Form 4 cluster and (V2) on directional SEC insider BUYING
in the last window_days; PENALTY on heavy insider selling. Institutional
ownership still adds a small boost. This gate never hard-rejects on its own --
absence of insider activity isn't bearish.

DATA: data["insider"] (SEC via openbb_source, injected at the finalist stage),
EDGAR Form 4 counts, yfinance institutional %. Degrades to neutral when
sources are unreachable.
"""
from data.ingest import edgar
from engine import fundamentals
from engine.config import load_config
from engine.types import GateResult

_CLUSTER = 3  # >= this many Form 4s in the window = cluster activity


def check(ticker, data):
    n4 = data.get("form4_count")
    if n4 is None:
        n4 = edgar.form4_count(ticker, days=90)

    info = data.get("info") or fundamentals.info(ticker)
    inst = info.get("heldPercentInstitutions")

    notes = []
    score = 5.0
    if n4 is None:
        notes.append("EDGAR unavailable")
    else:
        notes.append(f"{n4} Form 4s/90d")
        if n4 >= _CLUSTER:
            score += min(3.0, (n4 - _CLUSTER + 1) * 0.7)
            notes.append("insider cluster -> boost")

    if isinstance(inst, (int, float)):
        notes.append(f"{inst*100:.0f}% institutional")
        if inst >= 0.70:
            score += 1.0

    # V2: directional insider activity from SEC (openbb_source.insider_activity).
    ins = data.get("insider") or {}
    buys, sells = ins.get("buys"), ins.get("sells")
    if isinstance(buys, int) and isinstance(sells, int):
        icfg = load_config().get("insider", {})
        notes.append(f"SEC {icfg.get('window_days', 60)}d: {buys} buys / {sells} sells")
        if buys >= int(icfg.get("cluster_buys", 2)) and sells == 0:
            score += 2.0
            notes.append("insider buying cluster -> boost")
        elif sells >= int(icfg.get("heavy_sells", 3)) and sells > buys:
            score -= 2.0
            notes.append("heavy insider selling -> penalty")

    score = round(max(0.0, min(10.0, score)), 2)
    # Pass-through gate: always passes, score carries the conviction signal.
    return GateResult(True, score, f"Smart money: {'; '.join(notes)} (13F lag ~45d).")
