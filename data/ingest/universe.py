"""Universe construction: WHICH stocks the funnel scans.

Source of truth is the NASDAQ stock screener (one reliable request) which gives
price, consolidated volume, market cap, and SECTOR/industry for every US-listed
name. We then keep only names that are also tradable on Alpaca (so every
candidate can actually be ordered), and apply price + liquidity floors.

Sector tags ride along for free here -- Alpaca's asset list has no sector, and
yfinance can't bulk-fetch thousands of names without throttling. Price *bars*
for the funnel still come from Alpaca (primary) / yfinance (fallback).
"""
import json
import os
import time

import requests

from data.ingest import alpaca_source

_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
_CACHE = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, ".cache")


def _parse_money(s):
    """'$135.38' / '2410000000.00' / '' -> float (0.0 if unparseable)."""
    if not s:
        return 0.0
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except ValueError:
        return 0.0


def fetch_screener():
    """All US-listed names with price/volume/market-cap/sector from NASDAQ.

    Returns a list of dicts: ticker, price, volume, dollar_volume, market_cap,
    sector, industry.
    """
    r = requests.get(_SCREENER_URL, headers=_HEADERS,
                     params={"tableonly": "false", "limit": "10000",
                             "download": "true"}, timeout=60)
    r.raise_for_status()
    data = r.json()["data"]
    rows = data["rows"] if "rows" in data else data["table"]["rows"]

    from engine.sectors import to_gics

    out = []
    for row in rows:
        price = _parse_money(row.get("lastsale"))
        vol = int(row.get("volume") or 0)
        out.append({
            "ticker": row["symbol"].strip(),
            "price": price,
            "volume": vol,
            "dollar_volume": round(price * vol),
            "market_cap": round(_parse_money(row.get("marketCap"))),
            "sector": to_gics((row.get("sector") or "").strip()) or "",
            "industry": (row.get("industry") or "").strip(),
        })
    return out


def _norm(symbol):
    """Normalize share-class separators so NASDAQ and Alpaca symbols match."""
    return symbol.upper().replace("/", "-").replace(".", "-")


def build(min_price=10.0, min_dollar_volume=5_000_000, max_n=None,
          require_sector=True, require_alpaca_tradable=True):
    """Build the scan universe. Returns rows sorted by liquidity (desc).

    Keeps names priced >= min_price with daily $-volume >= min_dollar_volume
    (and a real sector, and Alpaca-tradable, when required). `max_n` optionally
    caps the count; otherwise it's whatever clears the floors.
    """
    rows = fetch_screener()

    tradable = None
    if require_alpaca_tradable and alpaca_source.is_configured():
        tradable = {_norm(s) for s in alpaca_source.list_equities()}

    kept = []
    for r in rows:
        if r["price"] < min_price:
            continue
        if r["dollar_volume"] < min_dollar_volume:
            continue
        if require_sector and not r["sector"]:
            continue
        if tradable is not None and _norm(r["ticker"]) not in tradable:
            continue
        kept.append(r)

    kept.sort(key=lambda r: r["dollar_volume"], reverse=True)
    return kept[:max_n] if max_n else kept


def sector_breakdown(rows):
    counts = {}
    for r in rows:
        counts[r["sector"]] = counts.get(r["sector"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def load_sector_map():
    """{ticker: sector} from the cached universe metadata (empty if absent)."""
    meta = os.path.join(_CACHE, "universe_meta.json")
    if not os.path.exists(meta):
        return {}
    with open(meta) as f:
        rows = json.load(f)
    return {r["ticker"]: r.get("sector") for r in rows}


def save(rows, path=None):
    os.makedirs(_CACHE, exist_ok=True)
    tickers_path = path or os.path.join(_CACHE, "universe.json")
    with open(tickers_path, "w") as f:
        json.dump([r["ticker"] for r in rows], f)
    with open(os.path.join(_CACHE, "universe_meta.json"), "w") as f:
        json.dump(rows, f)
    return tickers_path


def get_universe(max_age_days=7):
    """Return the watch-list of tickers, rebuilding only if it's stale.

    Loads the cached list when it's younger than `max_age_days`; otherwise
    rebuilds from the screener and re-saves. Price/liquidity floors are read
    from config.yaml so the universe always matches gate 1. This is how the
    weekly refresh happens automatically -- the nightly run calls this, and it
    only does real work once the saved list is a week old.
    """
    tickers_path = os.path.join(_CACHE, "universe.json")
    if os.path.exists(tickers_path):
        age = time.time() - os.path.getmtime(tickers_path)
        if age < max_age_days * 86400:
            with open(tickers_path) as f:
                return json.load(f)

    from engine.config import load_config
    cfg = load_config()
    try:
        rows = build(min_price=cfg.get("min_price", 5),
                     min_dollar_volume=cfg.get("liquidity_min_dollar_volume", 5_000_000))
        save(rows)
        return [r["ticker"] for r in rows]
    except Exception as e:  # screener/network down -> never strand the nightly run
        print(f"[universe] rebuild failed ({e}); falling back.")
        if os.path.exists(tickers_path):  # use the stale list if we have one
            with open(tickers_path) as f:
                return json.load(f)
        from data.ingest.sp500 import get_sp500_tickers
        return get_sp500_tickers()
