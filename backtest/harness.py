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
from data.ingest import universe as universe_src
from data.ingest.sp500 import get_sp500_tickers
from engine import voting
from engine.config import load_config
from engine.sectors import ALL_SECTOR_ETFS
from gates import (g0_regime, g1_liquidity, g2_trend, g3_sector,
                   g4_relative_strength, g5_3_priced_in, g5_setups,
                   g6_volume_flow)


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


# --- Hybrid backtest (technical subset) ----------------------------------
# Mirrors the live hybrid funnel using ONLY price/volume gates -- fundamentals
# (g5.5, g5.7, g6.5, g7, g7.5) have no point-in-time data on yfinance, so
# running them historically would leak look-ahead. The technical-subset is
# enough to calibrate `vote_threshold` and verify the math beats SPY before
# anything goes live.

_HYBRID_VOTERS = ["g2_trend", "g3_sector", "g4_rel_strength",
                  "g5.3_priced_in", "g6_volume_flow"]


def _rs_returns_at(asof, ticker_bars, lookback=127):
    out = []
    for df in ticker_bars.values():
        s = df.loc[:asof]
        if len(s) > lookback:
            out.append(float(s["close"].iloc[-1] / s["close"].iloc[-lookback] - 1))
    return out


def run_hybrid_backtest(universe=None, period="3y", vote_threshold=None, verbose=True):
    """Backtest the hybrid technical subset (no fundamentals -> no look-ahead).

    Guardrails (block on fail): g1_liquidity, g5_setups.
    Voters (weighted mean): g2_trend, g3_sector, g4_rel_strength,
        g5.3_priced_in, g6_volume_flow.

    A stock advances to a forward-return measurement only if all guardrails
    passed AND the weighted vote >= `vote_threshold` (defaults to
    config.funnel.vote_threshold).
    """
    cfg = load_config()
    funnel_cfg = cfg.get("funnel", {}) or {}
    if vote_threshold is None:
        vote_threshold = funnel_cfg.get("vote_threshold", 7.0)
    weights = funnel_cfg.get("default_weights", {}) or {}
    bt = cfg["backtest"]
    slippage = bt["slippage_pct"]
    hold = bt["hold_days"]
    step = bt["step_days"]
    min_bars = bt["min_history_bars"]

    if universe is None:
        universe = universe_src.get_universe()[: bt["universe_size"]]

    if verbose:
        print(f"[hybrid backtest] universe={len(universe)}, threshold={vote_threshold}, "
              f"hold={hold}d, step={step}d, slippage={slippage*100:.2f}%/side")
        print("[hybrid backtest] WARNING: SURVIVORSHIP BIAS (current universe used "
              "for all history) -- results are optimistic. Technical subset only.")

    vix = data_cache.get("^VIX", period=period)
    spx = data_cache.get("^GSPC", period=period)
    spy = data_cache.get("SPY", period=period)

    sector_etf_full = {e: data_cache.get(e, period=period) for e in ALL_SECTOR_ETFS}
    sector_by_t = universe_src.load_sector_map()

    bars_by_t = {}
    for t in universe:
        df = data_cache.get(t, period=period)
        if not df.empty and len(df) >= min_bars:
            bars_by_t[t] = df

    if verbose:
        print(f"[hybrid backtest] {len(bars_by_t)} tickers with sufficient history")

    alerts = []
    rejections = {"g0_regime": 0, "g1_liquidity": 0, "g5_setups": 0, "vote": 0}
    for t, df in bars_by_t.items():
        for pos in range(min_bars, len(df) - 1, step):
            asof = df.index[pos]
            bars = _slice(df, asof)
            _assert_no_lookahead(bars, asof)

            vix_s = _slice(vix, asof)
            spx_s = _slice(spx, asof)

            if not g0_regime.check("MARKET", {"vix": vix_s, "spx": spx_s}).passed:
                rejections["g0_regime"] += 1
                continue

            sector_etf_bars = {e: _slice(b, asof) for e, b in sector_etf_full.items()}
            rs_returns = _rs_returns_at(asof, bars_by_t)
            data = {
                "bars": bars, "vix": vix_s, "spx": spx_s,
                "sector": sector_by_t.get(t),
                "sector_etf_bars": sector_etf_bars,
                "rs_universe_returns": rs_returns,
            }

            if not g1_liquidity.check(t, data).passed:
                rejections["g1_liquidity"] += 1
                continue
            if not g5_setups.check(t, data).passed:
                rejections["g5_setups"] += 1
                continue

            scores = {
                "g2_trend":        g2_trend.check(t, data).score,
                "g3_sector":       g3_sector.check(t, data).score,
                "g4_rel_strength": g4_relative_strength.check(t, data).score,
                "g5.3_priced_in":  g5_3_priced_in.check(t, data).score,
                "g6_volume_flow":  g6_volume_flow.check(t, data).score,
            }
            vote = voting.compute_vote(scores, _HYBRID_VOTERS, weights)
            if vote < vote_threshold:
                rejections["vote"] += 1
                continue

            fwd = _forward_return(df, pos, hold, slippage)
            if fwd is None:
                continue
            spy_ret = _spy_window_return(spy, fwd["entry_date"], fwd["exit_date"], slippage)
            alerts.append({
                "ticker": t, "vote": round(vote, 2),
                **fwd,
                "spy_ret": spy_ret,
                "excess": fwd["ret"] - (spy_ret if spy_ret is not None else 0.0),
            })

    if verbose:
        print(f"[hybrid backtest] {len(alerts)} simulated alerts at threshold {vote_threshold}")
        print(f"[hybrid backtest] rejections: {rejections}")
    return pd.DataFrame(alerts)


def sweep_thresholds(thresholds=None, universe=None, period="3y", verbose=True):
    """Run the hybrid backtest at several thresholds; print/return a comparison.

    Higher threshold = fewer alerts, hopefully higher excess vs SPY.
    """
    thresholds = thresholds or [5.0, 6.0, 6.5, 7.0, 7.5]
    rows = []
    for thr in thresholds:
        df = run_hybrid_backtest(universe=universe, period=period,
                                 vote_threshold=thr, verbose=False)
        if df.empty:
            rows.append({"threshold": thr, "alerts": 0, "avg_ret": float("nan"),
                         "avg_spy": float("nan"), "excess": float("nan"),
                         "win_rate": float("nan")})
            continue
        valid_spy = df["spy_ret"].dropna()
        rows.append({
            "threshold": thr,
            "alerts": len(df),
            "avg_ret": df["ret"].mean(),
            "avg_spy": valid_spy.mean() if len(valid_spy) else float("nan"),
            "excess": df["excess"].mean(),
            "win_rate": (df["ret"] > 0).mean(),
        })
    out = pd.DataFrame(rows)
    if verbose:
        print("\n[threshold sweep] (technical-subset hybrid, current-universe survivorship-biased)")
        print(out.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    return out


if __name__ == "__main__":
    from backtest.report import print_report
    df = run_backtest()
    print_report(df)
