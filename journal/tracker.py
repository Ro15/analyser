"""Gate 12 -- journal / post-mortem tracker.

Logs every alert issued and tracks it to resolution (hit_target / invalidated /
time_stop), recording whether the catalyst actually happened. Persisted as
JSON-lines at .state/journal.jsonl (override with JOURNAL_PATH). A Postgres
table could back this in production; the file store keeps it runnable anywhere.
"""
import datetime as dt
import json
import os

_DEFAULT = os.path.join(os.path.dirname(__file__), os.pardir, ".state", "journal.jsonl")


def _path():
    return os.getenv("JOURNAL_PATH", _DEFAULT)


def _read():
    p = _path()
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_all(records):
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def log_alert(plan, *, setup=None, sector=None, regime=None, conviction=None,
              probability=None, scores=None, today=None, pipeline_version=None,
              size=None, kill_condition=None, debate=None):
    today = today or dt.date.today()
    rec = {
        "id": f"{plan['ticker']}-{today.isoformat()}",
        "ticker": plan["ticker"],
        "issued": today.isoformat(),
        "status": "open",
        "entry_zone": plan["entry_zone"],
        "reference_price": plan["reference_price"],
        "target": plan["target"],
        "time_stop": plan["time_stop"],
        "catalyst": plan.get("catalyst"),
        "setup": setup,
        "sector": sector,
        "regime": regime,
        "conviction": conviction,
        "p_target_90d": probability,
        "scores": scores,
        "pipeline_version": pipeline_version,
        "size": size,
        "kill_condition": kill_condition,
        "debate": debate,
        "postmortem_done": False,
        "resolution": None,
        "catalyst_happened": None,
        "realized_return": None,
        "resolved_on": None,
    }
    records = _read()
    if any(r["id"] == rec["id"] for r in records):
        return rec  # idempotent: don't double-log same ticker/day
    records.append(rec)
    _write_all(records)
    return rec


def resolve(alert_id, *, resolution, realized_return=None, catalyst_happened=None,
            on=None):
    records = _read()
    for r in records:
        if r["id"] == alert_id:
            r["status"] = "closed"
            r["resolution"] = resolution      # hit_target | invalidated | time_stop
            r["realized_return"] = realized_return
            r["catalyst_happened"] = catalyst_happened
            r["resolved_on"] = (on or dt.date.today()).isoformat()
    _write_all(records)


def set_fields(alert_id, **fields):
    """Merge arbitrary fields into one journal record (e.g. postmortem_done)."""
    records = _read()
    for r in records:
        if r["id"] == alert_id:
            r.update(fields)
    _write_all(records)


def open_alerts():
    return [r for r in _read() if r["status"] == "open"]


def all_alerts():
    return _read()


def mark_resolutions(price_lookup, today=None):
    """Resolve open alerts against current prices / time stops.

    price_lookup: callable(ticker) -> current price (or None).
    Hits target -> hit_target; past time_stop -> time_stop; else stays open.
    """
    today = today or dt.date.today()
    for r in open_alerts():
        px = price_lookup(r["ticker"])
        if px is None:
            continue
        ret = px / r["reference_price"] - 1
        if px >= r["target"]:
            resolve(r["id"], resolution="hit_target", realized_return=ret,
                    catalyst_happened=True, on=today)
        elif today.isoformat() >= r["time_stop"]:
            resolve(r["id"], resolution="time_stop", realized_return=ret, on=today)
