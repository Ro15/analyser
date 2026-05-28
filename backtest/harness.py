"""Backtest harness for the core gates (0,1,2,5).

Replays the gates against 3 years of daily data. For every sampled historical
date a stock passes ALL gates, records a simulated alert and tracks its forward
`hold_days` return. SPY's same-window return is recorded as the benchmark.

NO LOOK-AHEAD: on date t, gates see only bars with index <= t. The forward
return uses bars strictly AFTER t. This is asserted at runtime (see
_assert_no_lookahead).

SURVIVORSHIP BIAS: the universe is CURRENT S&P membership (yfinance), so names
that were delisted/removed never appear -> results are optimistic. The report
prints this warning prominently.
"""
import pandas as pd

from backtest import data_cache
from data.ingest.sp500 import get_sp500_tickers
from engine.config import load_config
from gates import g0_regime, g1_liquidity, g2_trend, g5_setups


def _slice(df, asof):
    """Bars with index <= asof (data available as of the alert date)."""
    return df.loc[:asof]


def _assert_no_lookahead(sliced, asof):
    if not sliced.empty:
        assert sliced.index[-1] <= asof, "LOOK-AHEAD: gate saw a future bar"


def _forward_return(df, entry_idx_pos, hold_days, slippage):
    """Return from the bar AFTER entry signal to the bar ~hold_days later.

    Entry fills at the next bar's close (no same-bar fill). Exit at the first
    bar on/after entry_date + hold_days. Slippage applied each side.
    """
    if entry_idx_pos + 1 >= len(df):
        return None  # no next bar to enter on
    entry_date = df.index[entry_idx_pos]
    entry_px = float(df["close"].iloc[entry_idx_pos + 1]) * (1 + slippage)

    exit_target_date = entry_date + pd.Timedelta(days=hold_days)
    future = df.index[df.index >= exit_target_date]
    if len(future) == 0:
        return None  # not enough forward data -> incomplete trade
    exit_date = future[0]
    exit_px = float(df.loc[exit_date, "close"]) * (1 - slippage)

    # Max favorable excursion (did it hit +target intra-hold?).
    hold_window = df.loc[df.index[entry_idx_pos + 1]:exit_date]
    mfe = float(hold_window["high"].max() / entry_px - 1) if not hold_window.empty else 0.0
    return {
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_px": entry_px,
        "exit_px": exit_px,
        "ret": exit_px / entry_px - 1,
        "mfe": mfe,
    }


def run_backtest(universe=None, period="3y", verbose=True):
    cfg = load_config()
    bt = cfg["backtest"]
    slippage = bt["slippage_pct"]
    hold = bt["hold_days"]
    step = bt["step_days"]
    min_bars = bt["min_history_bars"]

    if universe is None:
        universe = get_sp500_tickers()[: bt["universe_size"]]

    if verbose:
        print(f"[backtest] universe={len(universe)} names, "
              f"hold={hold}d, step={step}d, slippage={slippage*100:.2f}%/side")

    # Market + benchmark series (sliced per-date to avoid look-ahead).
    vix = data_cache.get("^VIX", period=period)
    spx = data_cache.get("^GSPC", period=period)
    spy = data_cache.get("SPY", period=period)

    alerts = []
    for t in universe:
        df = data_cache.get(t, period=period)
        if df.empty or len(df) < min_bars:
            continue
        # Sampled evaluation dates, leaving room for the forward window.
        positions = range(min_bars, len(df) - 1, step)
        for pos in positions:
            asof = df.index[pos]
            bars = _slice(df, asof)
            _assert_no_lookahead(bars, asof)
            data = {"bars": bars, "vix": _slice(vix, asof), "spx": _slice(spx, asof)}

            if not g0_regime.check(t, data).passed:
                continue
            if not g1_liquidity.check(t, data).passed:
                continue
            if not g2_trend.check(t, data).passed:
                continue
            setup = g5_setups.check(t, data)
            if not setup.passed:
                continue

            fwd = _forward_return(df, pos, hold, slippage)
            if fwd is None:
                continue
            # SPY benchmark over the identical window.
            spy_ret = _spy_window_return(spy, fwd["entry_date"], fwd["exit_date"], slippage)
            alerts.append({
                "ticker": t,
                "setup_score": setup.score,
                "setup": setup.reasoning,
                **fwd,
                "spy_ret": spy_ret,
                "excess": fwd["ret"] - (spy_ret if spy_ret is not None else 0.0),
            })

    if verbose:
        print(f"[backtest] {len(alerts)} simulated alerts recorded")
    return pd.DataFrame(alerts)


def _spy_window_return(spy, entry_date, exit_date, slippage):
    if spy is None or spy.empty:
        return None
    e = spy.index[spy.index >= entry_date]
    x = spy.index[spy.index >= exit_date]
    if len(e) == 0 or len(x) == 0:
        return None
    entry = float(spy.loc[e[0], "close"]) * (1 + slippage)
    exit_ = float(spy.loc[x[0], "close"]) * (1 - slippage)
    return exit_ / entry - 1


if __name__ == "__main__":
    from backtest.report import print_report
    df = run_backtest()
    print_report(df)
