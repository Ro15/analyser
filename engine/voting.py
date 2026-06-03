"""Shared voting math for the hybrid funnel.

The live funnel (engine/funnel.run) and the backtest harness both compute the
same weighted-mean vote, so the threshold the backtest validates is the same
threshold a live alert had to clear. Keeping this in one module prevents drift.
"""


def compute_vote(scores, voter_labels, weights):
    """Weighted mean of voter scores. Missing voters skipped; empty -> 0.0.

    scores: {gate_label: score_0_to_10}
    voter_labels: iterable of labels eligible to vote
    weights: {gate_label: weight}; missing labels fall back to 1.0
    """
    wsum = wden = 0.0
    for label in voter_labels:
        if label in scores:
            w = weights.get(label, 1.0)
            wsum += w * scores[label]
            wden += w
    return wsum / wden if wden else 0.0


def passes(vote, threshold):
    """Inclusive threshold check (>=)."""
    return vote >= threshold
