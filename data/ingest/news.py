"""NewsAPI (free tier) client. Key from .env; degrades to [] without a key.

LLM_MOCK=1 returns a deterministic canned headline so the news gate can run in
dry-run without a key or network.
"""
import datetime as dt
import os

import requests
from dotenv import load_dotenv

load_dotenv()


def recent_headlines(query, days=14, page_size=20):
    if os.getenv("LLM_MOCK") == "1":
        return [{"title": f"{query} unveils next-gen product ahead of launch event",
                 "description": "Analysts anticipate a catalyst in the coming weeks.",
                 "publishedAt": dt.date.today().isoformat(), "source": "MOCK"}]

    key = os.getenv("NEWSAPI_KEY")
    if not key:
        return []
    frm = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "from": frm, "language": "en",
                    "sortBy": "publishedAt", "pageSize": page_size, "apiKey": key},
            timeout=20,
        )
        r.raise_for_status()
        arts = r.json().get("articles", [])
        return [{"title": a.get("title"), "description": a.get("description"),
                 "publishedAt": a.get("publishedAt"),
                 "source": (a.get("source") or {}).get("name")} for a in arts]
    except requests.RequestException:
        return []
