"""Aggregate performance metrics from a backtest alerts DataFrame."""
import numpy as np

from engine.config import load_config


def compute_metrics(df):
    cfg = load_config()["backtest"]
    target = cfg["target_pct"]

    if df is None or df.empty:
        return {"alerts": 0}

    rets = df["ret"].to_numpy()
    spy = df["spy_ret"].dropna().to_numpy()
    excess = df["excess"].to_numpy()

    # Sharpe-like: mean/std of per-trade returns (not annualized; relative gauge).
    sharpe = float(np.mean(rets) / np.std(rets)) if np.std(rets) > 0 else 0.0

    return {
        "alerts": int(len(df)),
        "win_rate": float((rets > 0).mean()),
        "hit_target_rate": float((df["mfe"] >= target).mean()),
        "avg_return": float(np.mean(rets)),
        "median_return": float(np.median(rets)),
        "avg_spy_return": float(np.mean(spy)) if len(spy) else float("nan"),
        "avg_excess_vs_spy": float(np.mean(excess)),
        "pct_beating_spy": float((excess > 0).mean()),
        "max_drawdown_per_pick": float(np.min(rets)),
        "best_pick": float(np.max(rets)),
        "sharpe_like": sharpe,
    }
