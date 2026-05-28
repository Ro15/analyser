"""Gate 9.5 -- correlation / concentration filter (SET-LEVEL).

Caps redundant exposure across the final alert list:
  - at most `max_per_sector` alerts per sector
  - drops a name whose ~90-day return correlation with an already-accepted name
    exceeds `corr_max` (effectively the same bet)

Operates on the candidate SET (not a single ticker), so it exposes
`filter_candidates(...)` rather than the usual check().
"""
import numpy as np
import pandas as pd

MAX_PER_SECTOR = 2
CORR_MAX = 0.7
_WINDOW = 90


def _returns(bars):
    if bars is None or len(bars) < _WINDOW + 1:
        return None
    return bars["close"].pct_change().iloc[-_WINDOW:].reset_index(drop=True)


def filter_candidates(candidates, max_per_sector=MAX_PER_SECTOR, corr_max=CORR_MAX):
    """candidates: list of dicts with keys ticker, sector, total, _data(bars).
    Returns (kept, dropped) where dropped carries a reason. Highest-scoring
    names are considered first."""
    ordered = sorted(candidates, key=lambda c: c.get("total", 0), reverse=True)
    kept, dropped = [], []
    sector_counts = {}
    kept_returns = []

    for c in ordered:
        sector = c.get("sector") or "?"
        if sector_counts.get(sector, 0) >= max_per_sector:
            dropped.append({**c, "drop_reason": f"sector cap ({sector} already has "
                                                 f"{max_per_sector})"})
            continue

        rets = _returns((c.get("_data") or {}).get("bars"))
        redundant_with = None
        if rets is not None:
            for kt, kr in kept_returns:
                if len(kr) == len(rets):
                    corr = float(np.corrcoef(kr.values, rets.values)[0, 1])
                    if corr > corr_max:
                        redundant_with = (kt, corr)
                        break
        if redundant_with:
            dropped.append({**c, "drop_reason": f"corr {redundant_with[1]:.2f} > "
                                                 f"{corr_max} with {redundant_with[0]}"})
            continue

        kept.append(c)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if rets is not None:
            kept_returns.append((c["ticker"], rets))

    return kept, dropped
