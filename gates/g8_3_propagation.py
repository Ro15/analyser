"""Gate 8.3 -- catalyst propagation / read-through.

When a primary catalyst is detected on a name, related names (suppliers,
customers, competitors, sympathy) often move too. This module:
  - check(): pass-through gate that annotates a stock's read-through neighbours
  - propagate(): given finalists that HAVE a catalyst, returns connected tickers
    the raw scan may have missed, so the funnel can pull them in for review.

Graph-driven (catalyst/relationship_map). An LLM can later rank/justify the
read-through; kept deterministic here so it works without keys.
"""
from catalyst import relationship_map
from engine.types import GateResult


def check(ticker, data):
    neighbours = relationship_map.related(ticker)
    if not neighbours:
        return GateResult(True, 5.0, f"Propagation: no mapped relationships for {ticker}.")
    names = ", ".join(f"{t}({r})" for t, r in neighbours[:6])
    return GateResult(True, 6.0, f"Read-through chain: {names}.")


def propagate(catalyst_finalists):
    """catalyst_finalists: iterable of (ticker, catalyst_desc). Returns
    {new_ticker: reason} for connected names not already in the finalist set."""
    present = {t for t, _ in catalyst_finalists}
    added = {}
    for src, desc in catalyst_finalists:
        for dst, rel in relationship_map.related(src):
            if dst in present or dst in added:
                continue
            added[dst] = f"read-through from {src} ({rel}) -- catalyst: {desc}"
    return added
