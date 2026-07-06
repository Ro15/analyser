"""LLM wrappers for DeepSeek (cheap, news) and Claude (reasoning/veteran review).

Design goals (per CLAUDE.md):
  - keys ONLY from .env / environment, never hardcoded
  - robust JSON parsing + retries with backoff
  - a HARD monthly cost cap with logging (calls refused once exceeded)
  - graceful degradation: no key -> LLMUnavailable (gates fall back to neutral)
  - LLM_MOCK=1 -> deterministic canned responses so the pipeline runs end-to-end
    without any keys or network (used for dry-run demos + tests)

Implemented over plain `requests` to avoid extra SDK dependencies.
"""
import json
import os
import re
import time

import requests
from dotenv import load_dotenv

from engine.config import load_config

load_dotenv()

_STATE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, ".state")
_COST_FILE = os.path.join(_STATE_DIR, "llm_cost.json")

# Approx USD per 1M tokens (input, output). Rough; for cap accounting only.
_PRICES = {"deepseek": (0.27, 1.10), "claude": (5.0, 25.0)}


class LLMUnavailable(Exception):
    """Raised when a provider has no key (and not in mock mode)."""


def mock_mode():
    return os.getenv("LLM_MOCK") == "1"


def _month_key():
    import datetime as dt
    return dt.date.today().strftime("%Y-%m")


def _load_cost():
    try:
        with open(_COST_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def month_cost():
    return float(_load_cost().get(_month_key(), 0.0))


def _record_cost(usd):
    os.makedirs(_STATE_DIR, exist_ok=True)
    data = _load_cost()
    data[_month_key()] = round(data.get(_month_key(), 0.0) + usd, 6)
    with open(_COST_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _cap():
    return load_config()["llm"]["monthly_cost_cap_usd"]


def _check_cap():
    spent = month_cost()
    if spent >= _cap():
        raise LLMUnavailable(f"Monthly LLM cost cap reached (${spent:.2f} >= ${_cap():.2f}).")


def _estimate_cost(provider, in_tokens, out_tokens):
    pin, pout = _PRICES.get(provider, (0, 0))
    return (in_tokens / 1e6) * pin + (out_tokens / 1e6) * pout


def extract_json(text):
    """Pull the first JSON object out of an LLM response, tolerating prose/fences."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        candidate = brace.group(0) if brace else None
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _retry(fn, retries=3):
    delay = 2
    last = None
    for _ in range(retries):
        try:
            return fn()
        except requests.RequestException as e:
            last = e
            time.sleep(delay)
            delay *= 2
    raise LLMUnavailable(f"LLM request failed after retries: {last}")


def call_deepseek(system, user, json_mode=True, max_tokens=800):
    if mock_mode():
        return _mock_response("deepseek", user, system=system, json_mode=json_mode)
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise LLMUnavailable("DEEPSEEK_API_KEY not set.")
    _check_cap()
    model = load_config()["llm"]["deepseek_model"]

    def _do():
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                  "max_tokens": max_tokens,
                  **({"response_format": {"type": "json_object"}} if json_mode else {})},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()

    resp = _retry(_do)
    usage = resp.get("usage", {})
    _record_cost(_estimate_cost("deepseek",
                                usage.get("prompt_tokens", 0),
                                usage.get("completion_tokens", 0)))
    return resp["choices"][0]["message"]["content"]


def call_claude(system, user, max_tokens=1500):
    if mock_mode():
        return _mock_response("claude", user, system=system)
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise LLMUnavailable("ANTHROPIC_API_KEY not set.")
    _check_cap()
    model = load_config()["llm"]["claude_model"]

    def _do():
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()

    resp = _retry(_do)
    usage = resp.get("usage", {})
    _record_cost(_estimate_cost("claude",
                                usage.get("input_tokens", 0),
                                usage.get("output_tokens", 0)))
    return "".join(block.get("text", "") for block in resp.get("content", []))


def _mock_response(provider, user, system="", json_mode=True):
    """Deterministic canned response for dry-run / LLM_MOCK=1 (no key/network).

    Detects the kind of call from the system prompt so each gate gets a
    sensibly-shaped mock instead of a single hard-coded blob.
    """
    sys_lower = (system or "").lower()

    if not json_mode:
        return ("[MOCK thesis] Anticipated catalyst not yet priced in; healthy "
                "uptrend with a defined entry; risk/reward asymmetric.")

    # V2 debate + review mocks (must precede the provider=="claude" branch).
    if "bull" in sys_lower and "case" in sys_lower:
        return json.dumps({"case": "[MOCK BULL] Catalyst underappreciated; options "
                                   "flow and insiders align; base intact.",
                           "strongest_points": ["[MOCK] call buying",
                                                "[MOCK] insider cluster"]})
    if "bear" in sys_lower and "case" in sys_lower:
        return json.dumps({"case": "[MOCK BEAR] Move partly priced in; sector "
                                   "crowded; catalyst may slip.",
                           "strongest_points": ["[MOCK] run-up", "[MOCK] crowding"]})
    if "judge" in sys_lower:
        return json.dumps({"verdict": "take", "conviction": 7, "p_target_90d": 0.44,
                           "size": "half",
                           "kill_condition": "[MOCK] catalyst cancelled or guidance cut",
                           "reasoning": "[MOCK] Bear case largely priced in; "
                                        "asymmetric risk/reward."})
    if "post-mortem" in sys_lower:
        return json.dumps({"lesson": "[MOCK] Overweighted trend; catalyst timing slipped."})
    if "position review" in sys_lower:
        return json.dumps({"thesis_dead": False,
                           "reasoning": "[MOCK] Catalyst still scheduled; structure intact."})

    # Veteran-style review (used by g9; same prompt whether Claude or DeepSeek).
    if provider == "claude" or "veteran" in sys_lower or "conviction" in sys_lower:
        return json.dumps({
            "verdict": "would take", "conviction": 4,
            "probability_15pct_90d": 0.42,
            "thesis_risks": ["[MOCK] valuation re-rate", "[MOCK] catalyst slips"],
            "analogs": ["[MOCK] analog A +18%", "[MOCK] analog B +12%",
                        "[MOCK] analog C -5%"],
            "summary": "[MOCK] Constructive setup with defined invalidation."})

    # Default: news catalyst (g8).
    return json.dumps({
        "sentiment": "positive", "catalyst_type": "product_launch",
        "imminence": "coming", "red_flags": [],
        "summary": "[MOCK] Anticipated catalyst not yet reflected in price."})
