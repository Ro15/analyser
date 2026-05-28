"""Gate 1 -- liquidity.

Reject if avg daily dollar volume < liquidity_min_dollar_volume OR price < min_price.
`data['bars']` = the ticker's OHLCV DataFrame.
"""
from engine.config import load_config
from engine.indicators import dollar_volume
from engine.types import GateResult


def check(ticker, data):
    cfg = load_config()
    min_dv = cfg["liquidity_min_dollar_volume"]
    min_px = cfg["min_price"]

    bars = data.get("bars")
    if bars is None or bars.empty:
        return GateResult(False, 0.0, f"{ticker}: no price data.")

    price = float(bars["close"].iloc[-1])
    adv = dollar_volume(bars, window=20).iloc[-1]
    if adv is None or adv != adv:  # NaN -> not enough history
        adv = float((bars["close"] * bars["volume"]).mean())
    adv = float(adv)

    price_ok = price >= min_px
    dv_ok = adv >= min_dv
    passed = price_ok and dv_ok

    # Score scales with liquidity headroom, capped at 10.
    score = round(min(10.0, (adv / min_dv) * 5), 2) if passed else 0.0

    if passed:
        reason = f"Liquid: ${adv/1e6:.1f}M ADV >= ${min_dv/1e6:.0f}M, price ${price:.2f}."
    else:
        fails = []
        if not price_ok:
            fails.append(f"price ${price:.2f} < ${min_px}")
        if not dv_ok:
            fails.append(f"ADV ${adv/1e6:.1f}M < ${min_dv/1e6:.0f}M")
        reason = f"Illiquid: {'; '.join(fails)}."
    return GateResult(passed, score, reason)
