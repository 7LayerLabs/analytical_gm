"""The assistant GM's call on a trade: one answer, why in baseball terms, and what would change it.

Built on value.py. The analytics department's detailed review (trade_review.py) still runs
and sits underneath this call as "See the numbers"; its roster comparison and scouting
detail feed the plain-English pros and cons here.
"""

from collections import Counter

from value import dollars, value_engine

# Extra weight on wins this season, by the club's direction. A contender pays a premium for
# wins now; a seller gives them away cheaply. Value already counts this season's wins once.
WIN_NOW_PREMIUM = {
    "All in": 1.0,
    "Win now": 0.5,
    "Hold & evaluate": 0.0,
    "Retool": 0.0,
    "Selective sell": -0.5,
    "Rebuild": -0.5,
}
MIN_SCALE = 10_000_000  # small deals are judged against at least $10M so pennies don't swing it
CONTENDING = ("Win now", "All in")


def decide(edge, scale):
    """(call, strength) from our edge in dollars relative to the size of the deal."""
    ratio = edge / max(scale, MIN_SCALE)
    if ratio >= 0.15 and edge >= 5_000_000:
        return "Do it", "strong" if ratio >= 0.4 else "lean"
    if ratio >= 0:
        return "Do it", "lean"
    if ratio > -0.15:
        return "Do it if...", "lean"
    if ratio > -0.6 or -edge < 40_000_000:
        return "Don't", "strong" if ratio <= -0.3 else "lean"
    return "Hang up", "strong"


def trade_call(office, send, receive, mode, review=None):
    d = office.d
    engine = value_engine(d)
    outgoing = [engine.player(d.by_id[i]) for i in send]
    incoming = [engine.player(d.by_id[i]) for i in receive]

    def worth(v):
        return v.get("value", 0)

    give = sum(worth(v) for v in outgoing)
    get = sum(worth(v) for v in incoming)
    people = {x["player"]["id"]: x for x in (review or {}).get("people", [])}
    roles, holes, field_change = on_field(d, engine, review, [v["name"] for v in outgoing])
    wins_now = field_change * engine.season_left
    premium = WIN_NOW_PREMIUM.get(mode, 0.0) * wins_now * engine.dollars_per_war
    edge = get - give + premium
    call, strength = decide(edge, max(abs(give), abs(get)))

    future_salary = sum(s["salary"] for v in incoming for s in v.get("seasons", [])) - sum(
        s["salary"] for v in outgoing for s in v.get("seasons", [])
    )
    last_year = max(
        [s["year"] for v in outgoing + incoming for s in v.get("seasons", [])] or [d.year]
    )

    def line(v, ours):
        p = d.by_id[v["id"]]
        return scouting_line(p, people.get(v["id"]), roles.get(p["name"]), ours, v)

    pros, cons = [], []
    for v in incoming:
        if v.get("free_agent"):
            cons.append(f"{v['name']} is a free agent; he can't come over in a trade.")
        elif worth(v) >= 0:
            pros.append(line(v, ours=False))
        else:
            cons.append(f"We take on {v['name']}'s contract. {line(v, ours=False)}")
    for v in outgoing:
        if worth(v) > 0:
            cons.append(f"We lose {line(v, ours=True)}")
        else:
            pros.append(f"We get out from under {v['name']}'s deal: {contract_tail(v)}")
    cons.extend(holes)
    if wins_now >= 0.3:
        pros.append(f"Makes us about {wins_now:.1f} wins better over the rest of {d.year}.")
    elif wins_now <= -0.3:
        cons.append(f"Makes us about {-wins_now:.1f} wins worse over the rest of {d.year}.")
    if future_salary <= -1_000_000:
        pros.append(f"Cuts about {dollars(-future_salary)} of salary through {last_year}.")
    elif future_salary >= 1_000_000:
        cons.append(f"Adds about {dollars(future_salary)} of salary through {last_year}.")
    for i in list(send) + list(receive):
        if d.by_id[i].get("no_trade"):
            cons.append(f"{d.by_id[i]['name']} has a no-trade clause; he has to agree to it.")

    # A contender doesn't take a deal that makes it clearly worse this season, however good
    # the long-term value, unless the hole gets filled first.
    backfill = None
    if call == "Do it" and mode in CONTENDING and wins_now <= -0.75:
        backfill = max(outgoing, key=lambda v: v.get("war_this_season", 0))["name"]
        call, strength = "Do it if...", "lean"

    ask_for = (
        suggest_add(d, engine, receive, send, -edge) if call in ("Do it if...", "Don't") else []
    )
    if backfill:
        headline = (
            f"Good value ({dollars(get)} back), but it makes us about "
            f"{-wins_now:.1f} wins worse this year. Do it only if we can replace {backfill}."
        )
        fix = f"Line up {backfill}'s replacement first (another trade or a call-up), then make this deal."
    else:
        headline = headline_for(call, outgoing, give, get, edge, ask_for)
        fix = make_it_work(call, edge, ask_for)

    return {
        "call": call,
        "strength": strength,
        "headline": headline,
        "give": give,
        "get": get,
        "edge": round(edge, -5),
        "wins_now": round(wins_now, 1),
        "mode": mode,
        "give_players": [brief(v) for v in outgoing],
        "get_players": [brief(v) for v in incoming],
        "pros": pros,
        "cons": cons,
        "roster": roster_lines(review),
        "ask_for": ask_for,
        "make_it_work": fix,
        "price_of_a_win": engine.dollars_per_war,
        "salary_change": round(future_salary, -5),
        "salary_through": last_year,
    }


LINEUP = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
GROUPS = [
    ("Lineup vs righties", lambda role: role in LINEUP),
    ("Rotation", lambda role: role.startswith("SP")),
    ("Bullpen", lambda role: role.startswith("RP")),
]
TOOL_NAMES = {
    "contact": "contact",
    "gap": "gap power",
    "power": "power",
    "eye": "plate discipline",
    "strikeouts": "strikeout avoidance",
    "stuff": "stuff",
    "movement": "movement",
    "control": "control",
}


def names(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def roster_lines(review):
    """Who comes in and who goes out, the way you'd say it, not every slot that shuffles."""
    if not review:
        return []
    vs_righties = next((c for c in review.get("comparisons", []) if c["hand"] == "vsr"), None)
    changes = (vs_righties or {}).get("changes", [])
    lines = []
    for label, in_group in GROUPS:
        group = [c for c in changes if in_group(c["role"])]
        before = {c["before"]["name"]: c["role"] for c in group if c.get("before")}
        after = {c["after"]["name"]: c["role"] for c in group if c.get("after")}
        outs = [n for n in before if n not in after]
        ins = [n for n in after if n not in before]
        if not outs and not ins:
            continue
        parts = ([f"{names(outs)} out"] if outs else []) + ([f"{names(ins)} in"] if ins else [])
        if outs and not ins and any(c.get("before") and not c.get("after") for c in group):
            parts.append("nobody healthy to replace him")
        line = f"{label}: {', '.join(parts)}."
        moves = [f"{n} to {after[n]}" for n in after if n in before and after[n] != before[n]]
        if moves and label.startswith("Lineup"):  # pitchers sliding down a slot isn't news
            line = line[:-1] + f" ({', '.join(moves)})."
        lines.append(line)
    return lines


def group_of(role):
    return next((label for label, test in GROUPS if test(role)), None)


def on_field(d, engine, review, leaving=()):
    """Who plays instead of whom (vs righties): each player's role, any holes left, and the
    change in full-season wins. An empty slot means a replacement-level call-up, worth zero."""
    if not review:
        return {}, [], 0.0
    vsr = next((c for c in review.get("comparisons", []) if c["hand"] == "vsr"), None)
    roles, holes, change = {}, [], 0.0

    def rate(card):
        return engine.current_rate(d.by_id[card["id"]]) if card else 0.0

    for c in (vsr or {}).get("changes", []):
        before, after = c.get("before"), c.get("after")
        if before:
            roles.setdefault(before["name"], c["role"])
        if after:
            roles.setdefault(after["name"], c["role"])
        group = group_of(c["role"])
        if not group:
            continue  # bench shuffles don't move the needle
        change += rate(after) - rate(before)
        if before and not after:
            # Name the player we're trading, not whoever slid down into the empty slot.
            gone = [n for n in leaving if n in roles and group_of(roles[n]) == group]
            who = names(gone) if gone else before["name"]
            slot = "start every fifth day" if group == "Rotation" else "fill that spot"
            holes.append(
                f"Leaves a hole: with {who} gone, nobody healthy is ready to {slot}, "
                "so a replacement-level call-up does it."
            )
    for x in review.get("people", []):  # where the analytics review would play incoming players
        name, jobs = x["player"]["name"], x.get("jobs") or []
        if name not in roles and jobs:
            roles[name] = jobs[0].split(": ")[-1]
    return roles, holes, change


def avg3(x):
    return f"{x:.3f}".lstrip("0") if x is not None else "---"


def contract_tail(v):
    seasons = [s for s in v.get("seasons", []) if s["status"] != "minors"]
    if not seasons:
        return ""
    pay = sum(s["full_season_salary"] for s in seasons) / len(seasons)
    return f"{dollars(pay)} a year through {seasons[-1]['year']}."


def role_words(role, ours, p):
    """'our #2 starter', "he'd play 2B every day", ... from a roster-slot code."""
    if not role:
        if ours:
            return None
        if p.get("injured") or p.get("on_dl"):
            return "he'd join us once he's healthy"
        return (
            "he wouldn't crack our lineup"
            if p["kind"] == "bat"
            else "he wouldn't make our staff yet"
        )
    if role.startswith("SP"):
        n = role.split()[-1]
        return f"our #{n} starter" if ours else f"he'd slot in as our #{n} starter"
    if role.startswith("RP"):
        late = int(role.split()[-1]) <= 3
        if ours:
            return "one of our top relievers" if late else "a middle reliever"
        return "he'd pitch late innings for us" if late else "he'd pitch middle relief"
    if role.startswith("Bench"):
        return "a bench bat" if ours else "he'd come off our bench"
    return f"our everyday {role}" if ours else f"he'd play {role} every day"


def scouting_line(p, person, role, ours, v):
    """One sentence a GM would say: who he is for us, what he's done, his best tool, his deal."""
    o = (person or {}).get("observed") or {}
    tools = (person or {}).get("tools") or {}
    if p["kind"] == "bat":
        hand = {"L": "bats left", "R": "bats right", "S": "switch-hitter"}.get(p.get("bats"), "")
        stats = (
            f"{avg3(o.get('avg'))}/{avg3(o.get('obp'))}/{avg3(o.get('slg'))}, "
            f"{int(o.get('hr') or 0)} HR, {int(o.get('sb') or 0)} SB in {int(o['pa'])} PA this year"
            if o.get("pa")
            else "no big-league at-bats this year"
        )
    else:
        hand = {"L": "lefty", "R": "righty"}.get(p.get("throws"), "")
        stats = (
            f"{o['era']:.2f} ERA over {o['ip_display']} IP, {o.get('k_pct') or 0:.0%} strikeouts this year"
            if o.get("ip_display") and o.get("era") is not None
            else "no big-league innings this year"
        )
    who = role_words(role, ours, p)
    label = p["name"] + (f", {who}" if who and ours else "")
    extras = []
    if tools:
        best, rating = max(tools.items(), key=lambda kv: kv[1] or 0)
        if (rating or 0) >= 6:
            word = "elite" if rating >= 8 else "plus" if rating == 7 else "above-average"
            extras.append(f"{word} {TOOL_NAMES.get(best, best)} ({rating}/10)")
    if who and not ours:
        extras.append(who)
    if p.get("injured") or p.get("on_dl"):
        days = int(p.get("injury_days") or 0)
        extras.append(
            f"on the IL, back in about {days} day{'s' if days != 1 else ''}"
            if days
            else "hurt right now"
        )
    elif p.get("day_to_day"):
        extras.append("day-to-day")
    sentence = f"{label} ({hand}): {stats}" if hand else f"{label}: {stats}"
    if extras:
        sentence += "; " + "; ".join(extras)
    return (sentence + ". " + contract_tail(v)).strip()


def brief(v):
    return {
        "id": v["id"],
        "name": v["name"],
        "value": v.get("value", v.get("asking_value", 0)),
        "summary": v["summary"],
        "age": v.get("age"),
        "control_through": v.get("control_through"),
    }


def suggest_add(d, engine, receive, send, gap):
    """Real players on their side whose value would close the gap, closest first."""
    if gap <= 0:
        return []
    orgs = Counter(d.by_id[i]["organization_id"] or d.by_id[i]["team_id"] for i in receive)
    if not orgs:
        return []
    partner = orgs.most_common(1)[0][0]
    taken = set(receive) | set(send)
    options = []
    for p in d.profiles:
        if p["id"] in taken or p["free_agent"]:
            continue
        if (p["organization_id"] or p["team_id"]) != partner:
            continue
        v = engine.player(p)
        if v.get("value", 0) >= gap:
            options.append(v)
    options.sort(key=lambda v: v["value"])
    return [brief(v) for v in options[:3]]


def headline_for(call, outgoing, give, get, edge, ask_for):
    best_out = max(outgoing, key=lambda v: v.get("value", 0), default=None)
    if call == "Hang up":
        line = f"We'd give {dollars(give)} of value for {dollars(get)}."
        if len(outgoing) > 1 and best_out and best_out.get("value", 0) > 0.6 * give:
            line += f" {best_out['name']} alone is worth {dollars(best_out['value'])} to us."
        return line
    if call == "Don't":
        return f"We'd be overpaying by about {dollars(-edge)}."
    if call == "Do it if...":
        who = f", someone like {ask_for[0]['name']}" if ask_for else ""
        return f"Close. They need to add about {dollars(-edge)} more{who}."
    if edge >= 5_000_000:
        if give <= 0:
            shed = f" and shed {dollars(-give)} of bad money" if give < -1_000_000 else ""
            return f"We get {dollars(get)} of value for nothing we'll miss{shed}."
        return f"We get {dollars(get)} of value for {dollars(give)}."
    return "Fair deal, with a small edge to us."


def make_it_work(call, edge, ask_for):
    if call == "Do it" or edge >= 0:
        return None
    gap = dollars(-edge)
    if call == "Hang up":
        return f"Nothing realistic. They'd have to add about {gap} of value to make it even."
    listed = ", ".join(f"{a['name']} ({dollars(a['value'])})" for a in ask_for)
    if listed:
        return f"Ask them to add about {gap} more. Players on their side that would cover it: {listed}."
    return f"Ask them to add about {gap} more, or take something off our side."
