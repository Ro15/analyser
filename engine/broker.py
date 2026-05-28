"""Alpaca PAPER-trading integration.

HARD GUARDRAIL: this module talks ONLY to the paper endpoint
(paper-api.alpaca.markets). There is no live-trading code path here -- per
CLAUDE.md the first 6 months are paper-only. Keys come from .env.

Without keys it runs in SIMULATION: "fills" are recorded in the journal at the
plan's reference price, so the dashboard works end-to-end with no broker.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

PAPER_BASE = "https://paper-api.alpaca.markets"  # paper ONLY -- never live


def is_configured():
    return bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET"))


def _headers():
    return {"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
            "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET")}


def _assert_paper(base):
    assert base == PAPER_BASE and "paper" in base, "LIVE trading is forbidden"


def account():
    if not is_configured():
        return {"simulated": True, "cash": None}
    _assert_paper(PAPER_BASE)
    r = requests.get(f"{PAPER_BASE}/v2/account", headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def positions():
    if not is_configured():
        return []
    _assert_paper(PAPER_BASE)
    r = requests.get(f"{PAPER_BASE}/v2/positions", headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def place_paper_entry(plan, qty=1):
    """Submit a paper bracket order (entry + +15% take-profit), or simulate.

    Returns a dict describing the (simulated or real) order. Never live.
    """
    ticker = plan["ticker"]
    limit = plan["entry_zone"][1]
    target = plan["target"]

    if not is_configured():
        return {"simulated": True, "ticker": ticker, "qty": qty,
                "entry_limit": limit, "target": target,
                "note": "no Alpaca keys -> simulated fill at reference price"}

    _assert_paper(PAPER_BASE)
    order = {
        "symbol": ticker, "qty": qty, "side": "buy", "type": "limit",
        "time_in_force": "gtc", "limit_price": limit,
        "order_class": "oto",
        "take_profit": {"limit_price": target},
    }
    r = requests.post(f"{PAPER_BASE}/v2/orders", headers=_headers(),
                      json=order, timeout=20)
    r.raise_for_status()
    return r.json()
