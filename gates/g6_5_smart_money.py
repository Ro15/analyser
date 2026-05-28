"""Gate 6.5 -- smart money (insider / institutional).

Strong BOOST when there's an insider Form 4 cluster (and, where available,
institutional ownership is high/rising). This gate never hard-rejects on its
own -- absence of insider buying isn't bearish -- it only adds conviction.

DATA: SEC EDGAR Form 4 (timely) + yfinance institutional ownership %. 13F adds
lag ~45 days (noted). Degrades to neutral when EDGAR is unreachable.
"""
from data.ingest import edgar
from engine import fundamentals
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

    score = round(min(10.0, score), 2)
    # Pass-through gate: always passes, score carries the conviction signal.
    return GateResult(True, score, f"Smart money: {'; '.join(notes)} (13F lag ~45d).")
