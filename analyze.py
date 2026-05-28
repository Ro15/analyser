"""Single-stock Phase-1 analyzer.

Usage: python analyze.py NVDA

Runs gates 0,1,2,5 in sequence and prints a human-readable report:
each gate's pass/fail + score + reasoning, the matched setup, and a verdict.
Gate 0 is market-level: if the regime fails, no stock can alert tonight.
"""
import sys

from engine.dataset import build_data
from gates import g0_regime, g1_liquidity, g2_trend, g5_setups

GATES = [
    ("Gate 0  Regime", g0_regime),
    ("Gate 1  Liquidity", g1_liquidity),
    ("Gate 2  Trend", g2_trend),
    ("Gate 5  Setups", g5_setups),
]


def _line(char="-", n=72):
    return char * n


def analyze(ticker, with_breadth=False):
    ticker = ticker.upper()
    print(_line("="))
    print(f"  PHASE-1 ANALYSIS: {ticker}")
    print(_line("="))

    data = build_data(ticker, with_breadth=with_breadth)
    bars = data.get("bars")
    if bars is None or bars.empty:
        print(f"  No price data for {ticker}. Aborting.")
        return False
    print(f"  Loaded {len(bars)} daily bars "
          f"({bars.index[0].date()} -> {bars.index[-1].date()}), "
          f"last close ${float(bars['close'].iloc[-1]):.2f}\n")

    all_passed = True
    setup_desc = None
    for name, gate in GATES:
        res = gate.check(ticker, data)
        status = "PASS" if res.passed else "FAIL"
        print(f"  [{status}] {name:<18} score {res.score:>5.2f}")
        print(f"         {res.reasoning}")
        print()
        if gate is g5_setups and res.passed:
            setup_desc = res.reasoning
        if not res.passed:
            all_passed = False
            if gate is g0_regime:
                print("  >> Regime gate failed -> system-wide no-go. "
                      "No stock alerts tonight.\n")

    print(_line())
    if all_passed:
        print(f"  VERDICT: {ticker} PASSES all Phase-1 gates (0,1,2,5).")
        if setup_desc:
            print(f"           Setup -> {setup_desc}")
        print("           -> Phase-1 candidate. (Deeper gates come in later phases.)")
    else:
        print(f"  VERDICT: {ticker} does NOT pass Phase-1 gates. Filtered out.")
    print(_line())
    print()
    return all_passed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py TICKER [TICKER ...]")
        sys.exit(1)
    for tk in sys.argv[1:]:
        analyze(tk)
