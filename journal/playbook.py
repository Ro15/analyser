"""V2 lessons playbook: plain-text memory distilled from closed trades.

.state/playbook.md holds one "- [date TICKER resolution ret%] lesson" line per
closed trade (journal/postmortem.py appends). engine/debate.py hands
lessons_text() to the judge on every debate, so past mistakes inform every
future verdict. Compaction keeps the newest config playbook.max_lessons lines.
"""
import os

from engine.config import load_config

_DEFAULT = os.path.join(os.path.dirname(__file__), os.pardir, ".state", "playbook.md")


def _path():
    return os.getenv("PLAYBOOK_PATH", _DEFAULT)


def _lines():
    try:
        with open(_path()) as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]
    except FileNotFoundError:
        return []


def add_lesson(line):
    """Append one lesson; keep only the newest max_lessons."""
    cap = int(load_config().get("playbook", {}).get("max_lessons", 40))
    lines = (_lines() + [f"- {line}"])[-cap:]
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    with open(_path(), "w") as f:
        f.write("\n".join(lines) + "\n")


def lessons_text():
    """Playbook for the judge: '' when empty, else header + newest first."""
    lines = _lines()
    if not lines:
        return ""
    return f"({len(lines)} lessons, newest first)\n" + "\n".join(reversed(lines))
