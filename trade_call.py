"""The assistant GM's call on a trade: one answer, why, and what would change it.

Built on value.py. The analytics department's detailed review (trade_review.py) still runs
and sits underneath this call as "See the numbers".
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
MIN_SCALE = (
    10_000_000  # small deals are judged against at least $10M so pennies don't swing the call
)


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

    def wins(v):
        return v.get("war_this_season", 0)

    give = sum(worth(v) for v in outgoing)
    get = sum(worth(v) for v in incoming)
    wins_now = sum(wins(v) for v in incoming) - sum(wins(v) for v in outgoing)
    premium = WIN_NOW_PREMIUM.get(mode, 0.0) * wins_now * engine.dollars_per_war
    edge = get - give + premium
    scale = max(abs(give), abs(get))
    call, strength = decide(edge, scale)

    future_salary = sum(s["salary"] for v in incoming for s in v.get("seasons", [])) - sum(
        s["salary"] for v in outgoing for s in v.get("seasons", [])
    )
    last_year = max(
        [s["year"] for v in outgoing + incoming for s in v.get("seasons", [])] or [d.year]
    )

    pros, cons = [], []
    for v in incoming:
        if v.get("free_agent"):
            cons.append(f"{v['name']} is a free agent; he can't come over in a trade.")
        elif worth(v) >= 0:
            pros.append(f"{v['name']}: {v['summary']}")
        else:
            cons.append(f"We take on {v['name']}'s contract. {v['summary']}")
    for v in outgoing:
        if worth(v) > 0:
            cons.append(f"We give up {v['name']}. {v['summary']}")
        else:
            pros.append(f"We get out from under {v['name']}'s deal. {v['summary']}")
    if wins_now >= 0.3:
        pros.append(f"Adds about {wins_now:.1f} wins over the rest of {d.year}.")
    elif wins_now <= -0.3:
        cons.append(f"Costs us about {-wins_now:.1f} wins over the rest of {d.year}.")
    if future_salary <= -1_000_000:
        pros.append(f"Cuts about {dollars(-future_salary)} of salary through {last_year}.")
    elif future_salary >= 1_000_000:
        cons.append(f"Adds about {dollars(future_salary)} of salary through {last_year}.")
    for i in list(send) + list(receive):
        p = d.by_id[i]
        if p.get("no_trade"):
            cons.append(f"{p['name']} has a no-trade clause; he has to agree to it.")
        if i in receive and (p.get("injured") or p.get("on_dl")):
            cons.append(f"{p['name']} is hurt right now.")

    roster = roster_lines(review)
    ask_for = []
    if call in ("Do it if...", "Don't"):
        ask_for = suggest_add(d, engine, receive, send, -edge)
    headline = headline_for(call, outgoing, incoming, give, get, edge, ask_for)

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
        "roster": roster,
        "ask_for": ask_for,
        "make_it_work": make_it_work(call, edge, ask_for),
        "price_of_a_win": engine.dollars_per_war,
    }


LINEUP = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
GROUPS = [
    ("Lineup vs righties", lambda role: role in LINEUP),
    ("Rotation", lambda role: role.startswith("SP")),
    ("Bullpen", lambda role: role.startswith("RP")),
]


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
        line = f"{label}: {', '.join(parts)}."
        moves = [f"{n} to {after[n]}" for n in after if n in before and after[n] != before[n]]
        if moves and label.startswith("Lineup"):  # pitchers sliding down a slot isn't news
            line = line[:-1] + f" ({', '.join(moves)})."
        lines.append(line)
    return lines


def brief(v):
    return {
        "id": v["id"],
        "name": v["name"],
        "value": v.get("value", v.get("asking_value", 0)),
        "summary": v["summary"],
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


def headline_for(call, outgoing, incoming, give, get, edge, ask_for):
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
    if call in ("Do it",):
        return None
    gap = dollars(-edge)
    if call == "Hang up":
        return f"Nothing realistic. They'd have to add about {gap} of value to make it even."
    names = ", ".join(f"{a['name']} ({dollars(a['value'])})" for a in ask_for)
    if names:
        return (
            f"Ask them to add about {gap} more. Players on their side that would cover it: {names}."
        )
    return f"Ask them to add about {gap} more, or take something off our side."
