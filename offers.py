"""Line up several offers for the same player(s) and pick one, the way an assistant GM would.

Each offer gets the full trade call (trade_call.py). The offers are ranked by our edge
(value plus the win-now premium for the club's direction), and the verdict explains why the
winner beats the runner-up: more value, better for this season, cheaper, no hole.
"""

from trade_call import names, trade_call
from trade_review import analyze_trade
from value import dollars

TAKE = ("Do it",)
COUNTER = ("Do it if...",)


def offer_label(d, receive, given):
    if given:
        return given.strip()
    # Name the big-league club, not the affiliate a prospect happens to play for.
    clubs = {d.team_name(d.by_id[i]["organization_id"] or d.by_id[i]["team_id"]) for i in receive}
    return (clubs.pop() + " offer") if len(clubs) == 1 else "Multi-team offer"


def compare_offers(office, send, offers, mode):
    d = office.d
    if not send:
        raise ValueError("Choose who is on the block.")
    offers = [o for o in offers if o.get("receive")]
    if not 2 <= len(offers) <= 4:
        raise ValueError("Enter between two and four offers.")
    seen = {}
    rows = []
    for i, offer in enumerate(offers):
        receive = [int(x) for x in offer["receive"]]
        if set(receive) & set(send):
            raise ValueError("A player can't be on both sides of an offer.")
        label = offer_label(d, receive, offer.get("label"))
        if label in seen:  # two offers from the same club
            seen[label] += 1
            label = f"{label} #{seen[label]}"
        else:
            seen[label] = 1
        review = analyze_trade(office, send, receive, mode)
        call = trade_call(office, send, receive, mode, review)
        rows.append(
            {
                "label": label,
                "receive": receive,
                "call": call,
                "trade_review": review,
                "holes": sum("Leaves a hole" in c for c in call["cons"]),
            }
        )
    rows.sort(key=lambda r: r["call"]["edge"], reverse=True)
    tag(rows)
    best, runner = rows[0], rows[1]
    player = names([p["name"] for p in best["call"]["give_players"]])
    verdict = judge(best, runner, player, mode)
    return {
        "type": "Offers",
        "scenario_mode": mode,
        "on_the_block": best["call"]["give_players"],
        "give": best["call"]["give"],
        "offers": rows,
        "verdict": verdict,
        "recommendation": verdict["headline"],
        "why": verdict["headline"],
    }


def tag(rows):
    """Plain labels so the table reads at a glance."""
    most = max(rows, key=lambda r: r["call"]["get"])
    now = max(rows, key=lambda r: r["call"]["wins_now"])
    for r in rows:
        tags = []
        if r is most:
            tags.append("Most value")
        if r is now and r["call"]["wins_now"] > min(x["call"]["wins_now"] for x in rows) + 0.2:
            tags.append("Best for this year")
        if r["holes"]:
            tags.append("Leaves a hole")
        r["tags"] = tags


def judge(best, runner, player, mode):
    c, rc = best["call"], runner["call"]
    contending = mode in ("Win now", "All in")
    selling = mode in ("Selective sell", "Rebuild")
    reasons = []
    if c["get"] - rc["get"] >= 3_000_000:
        reasons.append(
            f"It brings back about {dollars(c['get'] - rc['get'])} more value than the {runner['label']}."
        )
    if not selling and c["wins_now"] - rc["wins_now"] >= 0.3:
        reasons.append(
            f"It's better for this season by about {c['wins_now'] - rc['wins_now']:.1f} wins"
            + (", which matters while we're contending." if contending else ".")
        )
    elif contending and rc["wins_now"] - c["wins_now"] >= 0.3:
        reasons.append(
            f"The {runner['label']} helps more this season (about {rc['wins_now'] - c['wins_now']:.1f} wins), "
            "but not by enough to make up the value gap."
        )
    if selling:
        mine, theirs = control(c), control(rc)
        if mine and theirs and (mine[0] <= theirs[0] - 2 or mine[1] > theirs[1]):
            reasons.append(
                f"It's younger (around {mine[0]:.0f}) and ours through {mine[1]}, which fits where we're headed."
            )
    if runner["holes"] and not best["holes"]:
        reasons.append(f"It doesn't leave the hole the {runner['label']} would.")
    if not reasons:
        reasons.append(
            f"It edges out the {runner['label']} by about {dollars(c['edge'] - rc['edge'])} once everything is counted."
        )

    if c["call"] in TAKE:
        call, headline = "Do it", f"Take the {best['label']}."
    elif c["call"] in COUNTER and c["edge"] >= 0:
        # The value is there; the only problem is the hole it leaves this season.
        call, headline = (
            "Do it if...",
            f"Take the {best['label']}, once {player}'s spot is covered.",
        )
        reasons.insert(0, c["make_it_work"])
    elif c["call"] in COUNTER:
        call, headline = "Do it if...", f"Counter the {best['label']}."
        if c.get("make_it_work"):
            reasons.insert(0, c["make_it_work"])
    else:
        call = "Don't"
        headline = f"Keep {player}. None of these is good enough."
        reasons = [
            (
                f"The best of them, the {best['label']}, still leaves us about {dollars(-c['edge'])} short."
                if c["edge"] < 0
                else f"The best of them, the {best['label']}, still doesn't clear the bar."
            )
        ]
        if c.get("make_it_work"):
            reasons.append(c["make_it_work"])
    return {"call": call, "strength": c["strength"], "headline": headline, "reasons": reasons}


def control(call):
    """(average age, last controlled year) of what an offer sends us."""
    players = [p for p in call["get_players"] if p.get("age")]
    if not players:
        return None
    return (
        sum(p["age"] for p in players) / len(players),
        max(p.get("control_through") or 0 for p in players),
    )
