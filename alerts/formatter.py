"""Format a structured plan + LLM verdicts into a Telegram alert message."""


def format_alert(plan, news=None, veteran=None, read_through=None):
    t = plan["ticker"]
    lines = [f"📈 *{t}* — catalyst-anticipation swing"]
    cat = plan.get("catalyst")
    if cat:
        lines.append(f"Catalyst: {cat['type']} in {cat['days_out']}d "
                     f"({cat['date']}) — {cat.get('description','')}")
    else:
        lines.append("Catalyst: none scheduled in window (technical setup)")

    ez = plan["entry_zone"]
    lines.append(f"Entry zone: ${ez[0]}–${ez[1]}  (ref ${plan['reference_price']})")
    lines.append(f"Target: ${plan['target']} (+{int(plan['target_pct']*100)}%)")
    lines.append(f"Scale-out: {plan['scale_out']}")
    lines.append("Invalidation exit:")
    for inv in plan["invalidation_exit"]:
        lines.append(f"  • {inv}")
    lines.append(f"Time stop: {plan['time_stop']}")

    if plan.get("conviction") is not None:
        p = plan.get("probability_15pct_90d")
        ptxt = f", p(+15%/90d) {p:.0%}" if isinstance(p, (int, float)) else ""
        lines.append(f"Conviction: {plan['conviction']}/5{ptxt}")
    if veteran:
        lines.append(f"Veteran: {veteran}")
    if news:
        lines.append(f"News: {news}")
    if read_through:
        lines.append(f"Read-through: {', '.join(read_through)}")
    return "\n".join(lines)
