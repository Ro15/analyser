"""V2 data enrichment via OpenBB (free, keyless providers only).

ALL OpenBB access lives here -- nothing else in the codebase imports openbb.
Every public fetcher:
  - returns a plain JSON-serializable dict, or None on ANY failure,
  - caches to .cache/obb/<TICKER>_<kind>.json with a per-kind TTL in days,
  - imports openbb lazily inside the fetch (the import is heavy; offline
    tests exercise the pure helpers + cache without it).
"""
import datetime as dt
import json
import os

_CACHE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                          ".cache", "obb")

_TTL_DAYS = {"short_volume": 1, "short_interest": 3, "options": 1,
             "insider": 1, "consensus": 1}


# ---------- cache plumbing ----------

def _cache_path(kind, ticker):
    return os.path.join(_CACHE_DIR, f"{ticker.upper()}_{kind}.json")


def _cache_get(kind, ticker):
    try:
        with open(_cache_path(kind, ticker)) as f:
            blob = json.load(f)
        age = (dt.date.today() - dt.date.fromisoformat(blob["as_of"])).days
        if age <= _TTL_DAYS[kind]:
            return blob["data"]
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        pass
    return None


def _cache_put(kind, ticker, data):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_cache_path(kind, ticker), "w") as f:
        json.dump({"as_of": dt.date.today().isoformat(), "data": data}, f)


def _fetch(kind, ticker, fn):
    """Cached value if fresh, else fn(); ANY exception -> None (gates go neutral)."""
    hit = _cache_get(kind, ticker)
    if hit is not None:
        return hit
    try:
        data = fn()
    except Exception:
        return None
    if data is not None:
        _cache_put(kind, ticker, data)
    return data


# ---------- pure computations (offline-testable) ----------

def _flow_metrics(chain):
    """(total_volume, call_put_volume_ratio) from an options-chain DataFrame
    with `option_type` in {call, put} and `volume` columns."""
    if chain is None or len(chain) == 0:
        return 0, None
    vol = chain["volume"].fillna(0)
    calls = float(vol[chain["option_type"] == "call"].sum())
    puts = float(vol[chain["option_type"] == "put"].sum())
    total = int(calls + puts)
    ratio = (calls / puts) if puts > 0 else None
    return total, ratio


def _expected_move(chain, spot, after_date):
    """Implied % move from the ATM straddle at the first expiry on/after
    `after_date` (ISO string/date; None -> today). -> (pct, expiry) or (None, None)."""
    if chain is None or len(chain) == 0 or not spot:
        return None, None
    after = str(after_date)[:10] if after_date else dt.date.today().isoformat()
    expiries = sorted({str(e)[:10] for e in chain["expiration"]})
    expiry = next((e for e in expiries if e >= after), None)
    if expiry is None:
        return None, None
    near = chain[chain["expiration"].astype(str).str.startswith(expiry)]
    legs = {}
    for typ in ("call", "put"):
        side = near[near["option_type"] == typ]
        if len(side) == 0:
            return None, None
        idx = (side["strike"] - spot).abs().idxmin()
        px = side.loc[idx, "last_trade_price"]
        if px is None or px != px:  # None/NaN
            return None, None
        legs[typ] = float(px)
    return round((legs["call"] + legs["put"]) / spot, 4), expiry


# ---------- public fetchers ----------

def short_volume(ticker):
    """{"short_pct": [oldest->newest floats 0-1]} for ~20 sessions, or None."""
    def _do():
        from openbb import obb
        df = obb.equity.shorts.short_volume(ticker, provider="stockgrid").to_dataframe()
        if "short_volume_percent" in df.columns:
            col = "short_volume_percent"
        else:
            df["pct"] = df["short_volume"] / df["total_volume"]
            col = "pct"
        df = df.sort_values("date").tail(20)
        pcts = [float(x) for x in df[col].tolist() if x == x]
        if pcts and max(pcts) > 1.5:          # provider reported 0-100
            pcts = [p / 100 for p in pcts]
        return {"short_pct": pcts} if pcts else None
    return _fetch("short_volume", ticker, _do)


def short_interest(ticker):
    """{"days_to_cover", "current", "previous"} from FINRA, or None."""
    def _do():
        from openbb import obb
        df = obb.equity.shorts.short_interest(ticker, provider="finra").to_dataframe()
        if df.empty:
            return None
        last = df.sort_values("settlement_date").iloc[-1]
        return {"days_to_cover": float(last["days_to_cover"]),
                "current": int(last["current_short_position"]),
                "previous": int(last["previous_short_position"])}
    return _fetch("short_interest", ticker, _do)


def options_snapshot(ticker, catalyst_date=None):
    """Flow metrics + implied expected move at the post-catalyst expiry, or None."""
    def _do():
        from openbb import obb
        chain = obb.derivatives.options.chains(ticker, provider="yfinance").to_dataframe()
        bars = obb.equity.price.historical(ticker, provider="yfinance").to_dataframe()
        spot = float(bars["close"].iloc[-1])
        total, ratio = _flow_metrics(chain)
        em, expiry = _expected_move(chain, spot, catalyst_date)
        return {"total_volume": total, "call_put_volume_ratio": ratio,
                "expected_move_pct": em, "expiry_used": expiry}
    return _fetch("options", ticker, _do)


def insider_activity(ticker, days=60):
    """{"buys": int, "sells": int} from SEC Form 4 filings, or None."""
    def _do():
        from openbb import obb
        df = obb.equity.ownership.insider_trading(
            ticker, provider="sec", limit=200).to_dataframe()
        if df.empty:
            return {"buys": 0, "sells": 0}
        cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        datecol = ("transaction_date" if "transaction_date" in df.columns
                   else "filing_date")
        df = df[df[datecol].astype(str) >= cutoff]
        if "acquisition_or_disposition" in df.columns:
            buys = int((df["acquisition_or_disposition"] == "A").sum())
            sells = int((df["acquisition_or_disposition"] == "D").sum())
        elif "transaction_type" in df.columns:
            tt = df["transaction_type"].astype(str).str.lower()
            buys = int(tt.str.contains("purchase|award").sum())
            sells = int(tt.str.contains("sale").sum())
        else:
            buys = sells = 0
        return {"buys": buys, "sells": sells}
    return _fetch("insider", ticker, _do)


def analyst_consensus(ticker):
    """Consensus target / recommendation via yfinance, or None."""
    def _do():
        from openbb import obb
        df = obb.equity.estimates.consensus(ticker, provider="yfinance").to_dataframe()
        if df.empty:
            return None
        r = df.iloc[0]

        def _f(key):
            v = r.get(key)
            return float(v) if isinstance(v, (int, float)) and v == v else None

        n = r.get("number_of_analysts")
        return {"target_consensus": _f("target_consensus"),
                "recommendation_mean": _f("recommendation_mean"),
                "n_analysts": int(n) if isinstance(n, (int, float)) and n == n else None}
    return _fetch("consensus", ticker, _do)
