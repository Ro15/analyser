"""Gate 5.3 -- "already priced in" detector (V2).

Two checks, cheap first:
  1. Price run-up: >= run_up_max over the lookback -> the move already
     happened -> REJECT (as in V1, thresholds now in config).
  2. Options expected move (finalist stage, when data["options"] present):
     the ATM straddle at the post-catalyst expiry is the move the market
     already expects. Implied >= our target -> the catalyst is priced in ->
     REJECT. Implied well below target -> our edge is NOT in the price ->
     bonus. This turns the bot's core thesis into a measurement.
"""
from engine.config import load_config
from engine.types import GateResult


def check(ticker, data):
    cfg = load_config()
    pcfg = cfg.get("priced_in", {})
    lookback = int(pcfg.get("lookback_days", 21))
    runup_max = float(pcfg.get("run_up_max", 0.10))
    edge_ratio = float(pcfg.get("edge_confirm_ratio", 0.6))
    target = float(cfg["backtest"]["target_pct"])

    bars = data.get("bars")
    if bars is None or len(bars) <= lookback:
        return GateResult(False, 0.0, f"{ticker}: insufficient history.")

    c = bars["close"]
    runup = float(c.iloc[-1] / c.iloc[-1 - lookback] - 1)
    if runup >= runup_max:
        return GateResult(False, 0.0,
                          f"Likely priced in: +{runup*100:.1f}% over {lookback}d "
                          f">= +{runup_max*100:.0f}% threshold.")

    frac = max(0.0, runup) / runup_max
    score = 10 * (1 - frac)
    notes = [f"run-up {runup*100:+.1f}%/{lookback}d ok"]

    em = (data.get("options") or {}).get("expected_move_pct")
    if isinstance(em, (int, float)):
        if em >= target:
            return GateResult(False, 0.0,
                              f"Priced in by options: implied move {em:.0%} >= "
                              f"target {target:.0%} "
                              f"(expiry {(data.get('options') or {}).get('expiry_used')}).")
        if em <= target * edge_ratio:
            score = min(10.0, score + 2.0)
            notes.append(f"options imply only {em:.0%} vs target {target:.0%} "
                         "-> edge not priced in")
        else:
            notes.append(f"options imply {em:.0%} (target {target:.0%})")

    return GateResult(True, round(score, 2), "Room to run: " + "; ".join(notes) + ".")
