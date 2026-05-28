"""Gate 7.5 -- earnings quality / accounting red flags.

REJECT if 3+ red flags fire:
  1) high accruals (net income >> operating cash flow)
  2) cash flow far below net income (CFO/NI < 0.7)
  3) rising DSO (receivables growing faster than revenue)
  4) high stock-based comp (SBC / revenue > 15%)
  5) buybacks funded by debt (repurchases while total debt rises)
Degrades to a neutral pass when statements are unavailable.
"""
from engine import fundamentals
from engine.types import GateResult


def _latest(series):
    if not series:
        return None
    for v in series:
        if v is not None:
            return v
    return None


def check(ticker, data):
    inc = data.get("income_stmt")
    if inc is None:
        inc = fundamentals.income_stmt(ticker)
    cf = data.get("cashflow")
    if cf is None:
        cf = fundamentals.cashflow(ticker)
    bs = data.get("balance_sheet")
    if bs is None:
        bs = fundamentals.balance_sheet(ticker)

    ni = fundamentals.row(inc, "Net Income", "NetIncome")
    rev = fundamentals.row(inc, "Total Revenue", "TotalRevenue")
    cfo = fundamentals.row(cf, "Operating Cash Flow", "OperatingCashFlow")
    sbc = fundamentals.row(cf, "Stock Based Compensation", "StockBasedCompensation")
    buyback = fundamentals.row(cf, "Repurchase Of Capital Stock", "RepurchaseOfCapitalStock")
    recv = fundamentals.row(bs, "Accounts Receivable", "AccountsReceivable", "Receivables")
    debt = fundamentals.row(bs, "Total Debt", "TotalDebt")

    flags, notes = [], []

    ni0, cfo0, rev0 = _latest(ni), _latest(cfo), _latest(rev)
    if ni0 and cfo0 is not None:
        if ni0 > 0 and cfo0 < ni0:
            flags.append("accruals"); notes.append("NI > CFO (accruals)")
        if ni0 > 0 and cfo0 / ni0 < 0.7:
            flags.append("low_cfo"); notes.append(f"CFO/NI {cfo0/ni0:.2f} < 0.7")

    if recv and rev and len(recv) >= 2 and len(rev) >= 2 and recv[1] and rev[1] and rev[0]:
        dso_now = recv[0] / rev[0]
        dso_prev = recv[1] / rev[1]
        if dso_now > dso_prev * 1.15:
            flags.append("dso"); notes.append("DSO rising >15%")

    if sbc and rev0:
        sbc0 = _latest(sbc)
        if sbc0 and abs(sbc0) / rev0 > 0.15:
            flags.append("sbc"); notes.append(f"SBC {abs(sbc0)/rev0*100:.0f}% of rev")

    if buyback and debt and len(debt) >= 2 and debt[0] and debt[1]:
        if _latest(buyback) and abs(_latest(buyback)) > 0 and debt[0] > debt[1] * 1.1:
            flags.append("debt_buyback"); notes.append("buybacks while debt +10%")

    if not notes and not (ni0 or rev0):
        return GateResult(True, 5.0, "Earnings quality: statements unavailable -> neutral pass.")

    passed = len(flags) < 3
    score = round(max(0.0, 10 - len(flags) * 3), 2)
    detail = "; ".join(notes) if notes else "no red flags"
    return GateResult(passed, score,
                      f"Earnings quality: {len(flags)} red flags [{detail}] "
                      f"-> {'OK' if passed else 'REJECT (>=3)'}.")
