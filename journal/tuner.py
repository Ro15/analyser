"""Adjust gate weights from rolling realized performance.

Learns a per-gate multiplier in [0.5, 1.5] from how the gate's score related to
realized outcomes across closed trades. Weights persist at .state/gate_weights.json
and are consumed when ranking survivors (a soft nudge, not a hard override).

This is intentionally conservative: small steps, clamped, and only acts once
there are enough closed trades to be meaningful.
"""
import json
import os

import numpy as np

from journal import tracker

_PATH = os.path.join(os.path.dirname(__file__), os.pardir, ".state", "gate_weights.json")
_MIN_TRADES = 20
_STEP = 0.1


def load_weights():
    try:
        with open(_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(weights):
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w") as f:
        json.dump(weights, f, indent=2)


def tune():
    """Nudge each gate's weight toward+ if its score correlates with winners."""
    closed = [r for r in tracker.all_alerts()
              if r.get("realized_return") is not None and r.get("scores")]
    if len(closed) < _MIN_TRADES:
        return {"status": f"need >= {_MIN_TRADES} closed trades, have {len(closed)}"}

    rets = np.array([r["realized_return"] for r in closed])
    gates = {g for r in closed for g in r["scores"]}
    weights = load_weights()
    for g in gates:
        xs = np.array([r["scores"].get(g, np.nan) for r in closed], dtype=float)
        mask = ~np.isnan(xs)
        if mask.sum() < _MIN_TRADES or np.std(xs[mask]) == 0:
            continue
        corr = float(np.corrcoef(xs[mask], rets[mask])[0, 1])
        w = weights.get(g, 1.0) + _STEP * np.sign(corr)
        weights[g] = float(np.clip(w, 0.5, 1.5))
    _save(weights)
    return {"status": "tuned", "weights": weights}


if __name__ == "__main__":
    print(tune())
