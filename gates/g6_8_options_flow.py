"""Gate 6.8 -- options flow (V2, finalist stage).

data["options"] = data.ingest.openbb_source.options_snapshot(...) or None.
Unusual call buying = someone expects the catalyst too (bullish boost);
heavy put buying = penalty. Thin/absent options market -> neutral pass
(never punish small caps for having no options).
Voter gate: never hard-rejects; score carries the signal.
"""
from engine.config import load_config
from engine.types import GateResult


def check(ticker, data):
    cfg = load_config().get("options_flow", {})
    min_vol = int(cfg.get("min_total_volume", 200))
    bull = float(cfg.get("call_put_bull", 2.0))
    bear = float(cfg.get("call_put_bear", 0.5))

    opt = data.get("options")
    if (not opt or (opt.get("total_volume") or 0) < min_vol
            or opt.get("call_put_volume_ratio") is None):
        return GateResult(True, 5.0,
                          "Options flow: no liquid options market -> neutral.")

    ratio = float(opt["call_put_volume_ratio"])
    if ratio >= bull:
        return GateResult(True, 8.0,
                          f"Options flow: bullish -- call/put volume {ratio:.1f} "
                          f">= {bull:.1f} (unusual call buying).")
    if ratio <= bear:
        return GateResult(True, 2.0,
                          f"Options flow: bearish -- call/put volume {ratio:.1f} "
                          f"<= {bear:.1f} (heavy put buying).")
    return GateResult(True, 5.0, f"Options flow: balanced (call/put {ratio:.1f}).")
