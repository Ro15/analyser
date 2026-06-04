"""Send alerts to a NEW Telegram bot (separate from any existing one).

Token + chat id come from .env (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID). When
they're absent the bot runs in DRY-RUN: messages are printed, not sent.

The formatter writes `*bold*` style markers; this module converts them to
Telegram-safe HTML before sending (legacy Markdown chokes on the `$`, `.`,
`(`, `-` characters in trade plans).
"""
import html
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()


def is_configured():
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _to_html(message):
    """Escape HTML-sensitive chars, then turn `*bold*` into <b>bold</b>."""
    escaped = html.escape(message, quote=False)
    return re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", escaped)


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
    body = {"chat_id": chat_id, "text": _to_html(message), "parse_mode": "HTML",
            "disable_web_page_preview": True}
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=body, timeout=20,
        )
        r.raise_for_status()
        return {"ok": True, "dry_run": False}
    except requests.RequestException as e:
        # Fall back to plain text so the alert at least gets through.
        print(f"[telegram] HTML send failed ({e}); retrying as plain text.")
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message,
                      "disable_web_page_preview": True},
                timeout=20,
            )
            r.raise_for_status()
            return {"ok": True, "dry_run": False, "fallback": "plain"}
        except requests.RequestException as e2:
            print(f"[telegram] plain send also failed: {e2}")
            return {"ok": False, "error": str(e2)}


def send_alerts(messages, dry_run=None):
    return [send(m, dry_run=dry_run) for m in messages]
