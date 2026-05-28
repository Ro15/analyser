"""Send alerts to a NEW Telegram bot (separate from any existing one).

Token + chat id come from .env (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID). When
they're absent the bot runs in DRY-RUN: messages are printed, not sent -- so the
nightly scan is fully demonstrable without credentials.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()


def is_configured():
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send(message, dry_run=None):
    """Send one message. dry_run defaults to True when not configured."""
    if dry_run is None:
        dry_run = not is_configured()

    if dry_run:
        print("----- [TELEGRAM DRY-RUN] -----")
        print(message)
        print("------------------------------")
        return {"ok": True, "dry_run": True}

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=20,
        )
        r.raise_for_status()
        return {"ok": True, "dry_run": False}
    except requests.RequestException as e:
        print(f"[telegram] send failed: {e}")
        return {"ok": False, "error": str(e)}


def send_alerts(messages, dry_run=None):
    return [send(m, dry_run=dry_run) for m in messages]
