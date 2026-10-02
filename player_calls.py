"""The assistant GM's call on signings, extensions and call-ups: one answer, in dollars and names.

Same scale as trades (Do it / Do it if... / Don't / Hang up). Built on value.py.
"""

from analytics import number
from trade_call import decide
from value import DISCOUNT, dollars, value_engine

FULL_TIME_GAIN = 0.5  # wins a season a newcomer must add over the incumbent to take the job
BENCH_SHARE = 0.4  # a player who wouldn't start gets about this share of a regular's playing time


def incumbent(d, engine, p):
    """The player on our big-league roster whose job this player would take, and his WAR rate."""
    role = engine.role(p)
    pool = [
        q
        for q in d.active()
        if q["id"] != p["id"]
        and engine.role(q) == role
        and (role != "bat" or q["position"] == p["position"])
    ]
    rated = sorted(((engine.current_rate(q), q) for q in pool), key=lambda x: -x[0])
    if not rated:
        return None, 0.0
    if role == "bat":
        rate, q = rated[0]  # the starter at his position
    else:
        slots = 5 if role == "sp" else 8  # the fifth starter or the last arm in the pen
        rate, q = rated[min(slots, len(rated)) - 1]
    return q, rate


def job_read(d, engine, p):
    """(would he start?, expected WAR share, plain line about who he'd replace)."""
    q, their_rate = incumbent(d, engine, p)
    mine = engine.current_rate(p)
    role = engine.role(p)
    job = {"bat": f"our {p['position']}", "sp": "a rotation spot", "rp": "a bullpen spot"}[role]
    if not q:
        return True, 1.0, f"He'd fill an empty spot: we have nobody active for {job}."
    gap = mine - their_rate
    if gap >= FULL_TIME_GAIN:
        return (
            True,
            1.0,
            f"He'd take {job} from {q['name']} ({mine:.1f} wins a season vs {their_rate:.1f}).",
        )
    if gap > -FULL_TIME_GAIN:
        return (
            False,
            0.5,
            f"He's about as good as {q['name']} ({mine:.1f} wins a season vs {their_rate:.1f}); they'd split time.",
        )
    return (
        False,
        BENCH_SHARE,
        f"He wouldn't take {job} from {q['name']} ({mine:.1f} wins a season vs {their_rate:.1f}).",
    )


def card(call, strength, headline, mode, pros, cons, ledger=None, make_it_work=None, engine=None):
    return {
        "call": call,
        "strength": strength,
        "headline": headline,
        "mode": mode,
        "ledger": ledger or [],
        "pros": pros,
        "cons": cons,
        "roster": [],
        "make_it_work": make_it_work,
        "price_of_a_win": engine.dollars_per_war if engine else None,
    }


def money_left(d):
    f = d.financials.get(d.team, {})
    budget, payroll = number(f.get("budget")), number(f.get("player_payroll"))
    return budget - payroll if budget else None


def signing_call(office, p, annual_offer, years, mode):
    d = office.d
    engine = value_engine(d)
    if not p["free_agent"]:
        return card(
            "Don't",
            "strong",
            f"{p['name']} isn't a free agent; he's under contract with {p['team']}. That's a trade.",
            mode,
            [],
            [],
            engine=engine,
        )
    starts, share, job = job_read(d, engine, p)
    length = max(1, min(6, years or recommended_length(engine, p)))
    seasons = engine.forecast(p, d.year + length - 1)
    weights = [DISCOUNT**i * (engine.season_left if i == 0 else 1.0) for i in range(len(seasons))]
    market = [s["war"] * share * engine.dollars_per_war for s in seasons]
    # Salary and value are both prorated for the part of this season that's left.
    worth_it = sum(w * m for w, m in zip(weights, market))
    fair = max(engine.league_min, worth_it / sum(weights))
    pros, cons = [], []
    wins = seasons[0]["war"] * share * engine.season_left if seasons else 0
    (pros if starts else cons).append(job)
    if seasons:
        pros.append(f"Projects around {seasons[0]['war']:.1f} wins a season as a regular.")
        if seasons[-1]["war"] < seasons[0]["war"] - 0.5:
            cons.append(
                f"He's {p['age']}; by {seasons[-1]['year']} we project him at {seasons[-1]['war']:.1f} wins."
            )
    room = money_left(d)
    if not annual_offer:
        if fair <= engine.league_min * 1.05 and not starts:
            return card(
                "Don't",
                "lean",
                f"Pass. {job} At most he's a minimum-salary depth piece.",
                mode,
                pros,
                cons,
                engine=engine,
            )
        headline = f"Sign him at up to {dollars(fair)} a year for {length} year{'s' if length > 1 else ''}."
        if room is not None and fair > room:
            cons.append(f"That's more than the {dollars(max(room, 0))} left in this year's budget.")
        return card(
            "Do it if...",
            "lean" if not starts else "strong",
            headline,
            mode,
            pros,
            cons,
            ledger=[{"label": "Fair price", "total": fair, "players": [], "note": "per year"}],
            make_it_work=f"Anything up to {dollars(fair)} a year is a fair deal; less is a win for us.",
            engine=engine,
        )
    cost = sum(annual_offer * w for w in weights)
    edge = worth_it - cost
    call, strength = decide(edge, max(cost, worth_it))
    if room is not None and annual_offer > room:
        cons.append(
            f"{dollars(annual_offer)} a year is more than the {dollars(max(room, 0))} left in this year's budget."
        )
    if edge >= 0:
        headline = f"{dollars(annual_offer)} a year is a good price. He's worth about {dollars(fair)} a year to us."
    else:
        headline = f"We'd be overpaying by about {dollars(-edge)}. He's worth about {dollars(fair)} a year to us."
    return card(
        call,
        strength,
        headline,
        mode,
        pros,
        cons,
        ledger=[
            {"label": "We pay", "total": cost, "players": [], "note": f"{years} years"},
            {
                "label": "We get",
                "total": worth_it,
                "players": [],
                "note": f"about {wins:.1f} wins the rest of this year",
            },
        ],
        make_it_work=None if edge >= 0 else f"Offer no more than {dollars(fair)} a year.",
        engine=engine,
    )


def recommended_length(engine, p):
    """Sign through the seasons he projects as a solid regular, up to six."""
    seasons = engine.forecast(p, engine.year + 5)
    useful = [s for s in seasons if s["war"] >= 1.5]
    return max(1, len(useful))


def extension_call(office, p, annual_offer, years, start_year, mode):
    d = office.d
    engine = value_engine(d)
    v = engine.player(p)
    controlled = {s["year"]: s["full_season_salary"] for s in v.get("seasons", [])}
    through = v.get("control_through") or d.year
    start = start_year or d.year + 1
    if not years:
        # Cover him through age 33, and always at least three years past his current deal.
        turns_33 = d.year + (33 - int(p["age"]))
        years = max(2, min(12, max(turns_33, through + 3) - start + 1))
    length = years
    span = range(start, start + length)
    forecast = {s["year"]: s for s in engine.forecast(p, start + length - 1)}
    base = []
    for i, y in enumerate(span):
        market = forecast[y]["war"] * engine.dollars_per_war
        base.append((DISCOUNT ** (y - d.year), controlled.get(y, market), y in controlled, y))
    fair = sum(w * b for w, b, _, _ in base) / sum(w for w, _, _, _ in base)
    free_years = [y for _, _, c, y in base if not c]
    pros, cons = [], []
    if free_years:
        pros.append(
            f"Locks him up through {span[-1]}: {len(free_years)} season{'s' if len(free_years) > 1 else ''} "
            f"he'd otherwise reach free agency ({free_years[0]}-{free_years[-1]})."
        )
    else:
        return card(
            "Don't",
            "lean",
            f"No need. He's already ours through {through}; this deal would only change what we pay him.",
            mode,
            [],
            [f"Every year of this offer is already under our control (through {through})."],
            make_it_work=f"Revisit when he's a year or two from free agency, or add years past {through}.",
            engine=engine,
        )
    last = forecast[span[-1]]
    if last["war"] < forecast[span[0]]["war"] - 0.75:
        cons.append(
            f"By {span[-1]} he's {last['age']} and projects at {last['war']:.1f} wins; the back end is the risk."
        )
    pros.append(f"Projects around {forecast[span[0]]['war']:.1f} wins in {span[0]}.")
    if not annual_offer:
        offer = 0.9 * fair  # a good extension buys certainty at a discount
        return card(
            "Do it if...",
            "strong" if free_years else "lean",
            f"Offer up to {dollars(offer)} a year for {length} years ({span[0]}-{span[-1]}). Above {dollars(fair)} a year we're overpaying.",
            mode,
            pros,
            cons,
            ledger=[
                {"label": "Good offer", "total": offer, "players": [], "note": "per year"},
                {"label": "Break-even", "total": fair, "players": [], "note": "per year"},
            ],
            make_it_work=f"Start around {dollars(0.8 * fair)} a year; walk away above {dollars(fair)}.",
            engine=engine,
        )
    edge = sum(w * (b - annual_offer) for w, b, _, _ in base)
    total = sum(w * annual_offer for w, _, _, _ in base)
    call, strength = decide(edge, total)
    raise_now = [y for _, b, c, y in base if c and annual_offer > b * 1.25]
    if raise_now:
        cons.append(
            f"Pays him more than he'd cost us anyway in {raise_now[0]}-{raise_now[-1]}, while we still control him."
        )
    headline = (
        f"Good price. We save about {dollars(edge)} against what he'd cost us otherwise."
        if edge >= 0
        else f"Too rich by about {dollars(-edge)}. Break-even is {dollars(fair)} a year."
    )
    return card(
        call,
        strength,
        headline,
        mode,
        pros,
        cons,
        ledger=[
            {"label": "We pay", "total": annual_offer, "players": [], "note": "per year"},
            {"label": "Break-even", "total": fair, "players": [], "note": "per year"},
        ],
        make_it_work=None if edge >= 0 else f"Bring it down to {dollars(0.9 * fair)} a year.",
        engine=engine,
    )


def promotion_call(office, p, mode):
    d = office.d
    engine = value_engine(d)
    starts, _, job = job_read(d, engine, p)
    mine = engine.current_rate(p)
    pros, cons = [], []
    v = engine.player(p)
    if p.get("injured") or p.get("on_dl"):
        return card(
            "Don't",
            "strong",
            f"Not yet. {p['name']} is hurt.",
            mode,
            [],
            [f"{p['name']} is injured."],
            engine=engine,
        )
    (pros if starts else cons).append(job)
    if v.get("summary"):
        pros.append(v["summary"])
    if starts:
        headline = "Call him up. He's already better than the guy he'd replace."
        call, strength = "Do it", "strong" if mine >= 2 else "lean"
    elif mine >= 1.0:
        blocker = incumbent(d, engine, p)[0]
        who = blocker["name"] if blocker else "the starter ahead of him"
        headline = f"He's ready, but {who} is better right now. Call him up when that changes."
        call, strength = "Do it if...", "lean"
        cons.append("A part-time role in the majors would slow his development.")
    else:
        headline = f"Not yet. He projects at {mine:.1f} wins a season right now."
        call, strength = "Don't", "strong" if mine < 0.5 else "lean"
    if call != "Do it":
        make = "Call him up the moment the starter ahead of him gets hurt or slumps."
    else:
        make = None
    if p["service_years"] == 0 and call == "Do it":
        cons.append("Starts his big-league service clock.")
    return card(call, strength, headline, mode, pros, cons, make_it_work=make, engine=engine)
