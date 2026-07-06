"""V2 finalist enrichment: the expensive per-ticker OpenBB fetches run ONLY on
the top-N survivors (config llm.max_finalists), injected into each survivor's
shared `_data` dict so the finalist gates (5.3, 6.5, 6.7, 6.8) can score them.
Every fetcher already degrades to None on failure -> gates go neutral."""
from data.ingest import openbb_source


def enrich_finalists(survivors, top_n):
    finalists = survivors[:top_n]
    for s in finalists:
        t = s["ticker"]
        d = s.setdefault("_data", {})
        cat = s.get("catalyst") or {}
        d["short_volume"] = openbb_source.short_volume(t)
        d["short_interest"] = openbb_source.short_interest(t)
        d["options"] = openbb_source.options_snapshot(t, catalyst_date=cat.get("date"))
        d["insider"] = openbb_source.insider_activity(t)
        d["consensus"] = openbb_source.analyst_consensus(t)
        d["gate_scores"] = s.get("scores", {})
    return finalists
