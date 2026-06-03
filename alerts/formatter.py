"""Format a structured plan + LLM verdicts into a Telegram alert message.

The message tells you WHY this stock cleared the funnel: the per-gate
reasonings (top voters), the catalyst, the news verdict, the trade plan, and
the structural exits. That way the alert is self-explanatory on your phone.
"""

# Gates whose reasoning is most useful to a human reading the alert. Ordered
# so the catalyst-relevant / setup ones come first.
_WHY_GATES = [
    ("g5_setups",       "Setup"),
    ("g2_trend",        "Trend"),
    ("g4_rel_strength", "Strength vs market"),
    ("g3_sector",       "Sector momentum"),
    ("g5.3_priced_in",  "Not yet priced-in"),
    ("g6_volume_flow",  "Volume flow"),
    ("g5.7_fundamentals", "Fundamentals"),
    ("g6.5_smart_money", "Smart money"),
    ("g7.5_earnings_quality", "Earnings quality"),
]


def _why_lines(reasonings, scores, limit=5):
    """Pick the top voter reasons (by score) for the 'Why this stock' section."""
    if not reasonings:
        return []
    ranked = []
    for label, pretty in _WHY_GATES:
        r = reasonings.get(label)
        s = (scores or {}).get(label)
        if not r:
            continue
        ranked.append((s if isinstance(s, (int, float)) else 5.0, pretty, r))
    ranked.sort(key=lambda x: x[0], reverse=True)
    out = []
    for _score, pretty, reason in ranked[:limit]:
        out.append(f"  • {pretty}: {reason}")
    return out


def format_alert(plan, news=None, veteran=None, read_through=None,
                 reasonings=None, vote=None, sector=None, scores=None):
    t = plan["ticker"]
    header = f"📈 *{t}* — catalyst-anticipation swing"
    if vote is not None:
        meta_bits = []
        if sector:
            meta_bits.append(sector)
        meta_bits.append(f"Vote: {vote:.2f}/10")
        header += "\n" + " | ".join(meta_bits)
    lines = [header]

    cat = plan.get("catalyst")
    if cat:
        lines.append(f"\nCatalyst: {cat['type']} in {cat['days_out']}d "
                     f"({cat['date']}) — {cat.get('description','')}")
    else:
        lines.append("\nCatalyst: none scheduled in window (technical setup)")

    why = _why_lines(reasonings, scores or (plan.get("scores") if isinstance(plan, dict) else None))
    if why:
        lines.append("\n*Why this stock:*")
        lines.extend(why)

    if news:
        lines.append(f"\n*News (AI):* {news}")

    lines.append("\n*Trade plan:*")
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
        lines.append(f"\n*Veteran review:* {veteran}")
    if read_through:
        lines.append(f"\nRead-through: {', '.join(read_through)}")
    return "\n".join(lines)
