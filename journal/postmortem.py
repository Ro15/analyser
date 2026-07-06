"""V2 post-mortem: one short lesson per newly closed trade (win OR lose),
appended to the lessons playbook the judge reads before every debate.

Runs nightly after resolutions. No LLM available -> stop silently; the
records keep postmortem_done=False so tomorrow retries. V1-era closed trades
get lessons too on the first run."""
import json

from engine import llm_client
from journal import playbook, tracker

_SYS = (
    "You write a one-sentence post-mortem lesson for a closed swing trade so "
    "future picks improve. Focus on what the gates and debate missed or got "
    "right. Respond ONLY with JSON: {\"lesson\":\"...\"}"
)


def _prompt(rec):
    keep = {k: rec.get(k) for k in
            ("ticker", "issued", "resolution", "realized_return", "scores",
             "catalyst", "setup", "kill_condition")}
    bear = (rec.get("debate") or {}).get("bear_case")
    if bear:
        keep["bear_case_at_entry"] = bear
    return json.dumps(keep, default=str)


def run(verbose=True):
    todo = [r for r in tracker.all_alerts()
            if r["status"] == "closed" and not r.get("postmortem_done")]
    done = 0
    for rec in todo:
        try:
            raw = llm_client.call_deepseek(_SYS, _prompt(rec), max_tokens=200)
        except llm_client.LLMUnavailable:
            break  # no model tonight; try again tomorrow
        lesson = (llm_client.extract_json(raw) or {}).get("lesson")
        if not lesson:
            continue
        ret = rec.get("realized_return")
        ret_txt = f"{ret*100:+.0f}%" if isinstance(ret, (int, float)) else "?"
        playbook.add_lesson(f"[{rec.get('resolved_on')} {rec['ticker']} "
                            f"{rec.get('resolution')} {ret_txt}] {lesson}")
        tracker.set_fields(rec["id"], postmortem_done=True)
        done += 1
    if verbose and todo:
        print(f"[postmortem] wrote {done}/{len(todo)} lessons")
    return done
