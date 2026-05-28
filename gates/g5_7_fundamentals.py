"""Gate 5.7 -- fundamental quality.

PASS only if: revenue growth stable/accelerating, FCF positive & growing, gross
margins stable/expanding. Degrades to a neutral pass when statements are missing
(common for yfinance on some names) rather than crashing.
"""
from engine import fundamentals
from engine.types import GateResult


def _yoy_growth(series):
    """series newest-first; returns list of YoY growth rates oldest->newest."""
    if not series or len(series) < 2:
        return None
    vals = [v for v in series if v is not None]
    if len(vals) < 2:
        return None
    chron = list(reversed(vals))  # oldest first
    growth = []
    for a, b in zip(chron, chron[1:]):
        if a and a != 0:
            growth.append(b / a - 1)
    return growth or None


def check(ticker, data):
    inc = data.get("income_stmt")
    if inc is None:
        inc = fundamentals.income_stmt(ticker)
    cf = data.get("cashflow")
    if cf is None:
        cf = fundamentals.cashflow(ticker)

    rev = fundamentals.row(inc, "Total Revenue", "TotalRevenue")
    gp = fundamentals.row(inc, "Gross Profit", "GrossProfit")
    fcf = fundamentals.row(cf, "Free Cash Flow", "FreeCashFlow")
    if fcf is None:
        ocf = fundamentals.row(cf, "Operating Cash Flow", "OperatingCashFlow")
        capex = fundamentals.row(cf, "Capital Expenditure", "CapitalExpenditures")
        if ocf and capex:
            fcf = [o + c for o, c in zip(ocf, capex)]  # capex is negative

    rev_g = _yoy_growth(rev)
    checks, notes = [], []

    if rev_g:
        ok = rev_g[-1] > 0 and (len(rev_g) < 2 or rev_g[-1] >= rev_g[-2] - 0.02)
        checks.append(ok)
        notes.append(f"rev YoY {rev_g[-1]*100:+.0f}% ({'accel/stable' if ok else 'decel'})")

    if fcf:
        latest = fcf[0]
        prior = fcf[1] if len(fcf) > 1 else None
        ok = latest is not None and latest > 0 and (prior is None or latest >= prior)
        checks.append(ok)
        notes.append(f"FCF {'positive&growing' if ok else 'weak/negative'}")

    if gp and rev and len(gp) >= 2 and len(rev) >= 2 and rev[0] and rev[1]:
        gm_now = gp[0] / rev[0]
        gm_prev = gp[1] / rev[1]
        ok = gm_now >= gm_prev - 0.01
        checks.append(ok)
        notes.append(f"gross margin {gm_now*100:.0f}% ({'stable/up' if ok else 'down'})")

    if not checks:
        return GateResult(True, 5.0, "Fundamentals unavailable -> neutral pass.")

    passed = all(checks)
    score = round(10 * sum(checks) / len(checks), 2)
    return GateResult(passed, score,
                      f"Fundamentals {'OK' if passed else 'weak'}: {'; '.join(notes)}.")
