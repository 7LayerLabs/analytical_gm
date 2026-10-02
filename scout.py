"""Scout & fit: pick players from anywhere and get the assistant GM's scouting report on each,
plus how he'd fit on our club: tools, this year's line with league rank, recent history, age and
development, Fenway fit, whose job he'd take, what he'd cost and what he's worth to us.
"""

from analytics import number
from moves import LEVELS, Moves, stat_text
from player_calls import incumbent, job_read
from readiness import ReadinessDesk
from value import dollars

TOOL_WORD = {10: "elite", 9: "elite", 8: "elite", 7: "plus", 6: "above-average", 5: "average"}
BAT_TOOLS = [
    ("contact", "contact"),
    ("gap", "gap power"),
    ("power", "power"),
    ("eye", "plate discipline"),
    ("strikeouts", "strikeout avoidance"),
]
PIT_TOOLS = [("stuff", "stuff"), ("movement", "movement"), ("control", "control")]
POSITION_CODES = {"C": 2, "1B": 3, "2B": 4, "3B": 5, "SS": 6, "LF": 7, "CF": 8, "RF": 9}


def word(v):
    v = int(number(v))
    return TOOL_WORD.get(v, "fringe" if v == 4 else "weak")


def join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def sentence(text):
    return text[0].upper() + text[1:] if text else text


class Scout:
    def __init__(self, office):
        self.o, self.d = office, office.d
        self.m = Moves(office)
        self.e = self.m.e
        self.desk = ReadinessDesk(self.d, self.d.team)
        self.home = self.d.parks.get(self.d.teams.get(self.d.team, {}).get("park_id"), {})

    # ---- pieces --------------------------------------------------------------------------

    def tool_grid(self, p):
        """[{tool, now, ceiling}] on the 1-10 scale."""
        if p["kind"] == "bat":
            r = self.d.ratings["players_batting"].get(p["id"], {})
            pairs = [
                (label, r.get(f"batting_ratings_overall_{k}"), r.get(f"batting_ratings_talent_{k}"))
                for k, label in BAT_TOOLS
            ]
            code = POSITION_CODES.get(p["position"])
            if code:
                f = self.d.ratings["players_fielding"].get(p["id"], {})
                pairs.append(
                    (
                        f"defense at {p['position']}",
                        f.get(f"fielding_rating_pos{code}"),
                        f.get(f"fielding_rating_pos{code}_pot"),
                    )
                )
        else:
            r = self.d.ratings["players_pitching"].get(p["id"], {})
            pairs = [
                (
                    label,
                    r.get(f"pitching_ratings_overall_{k}"),
                    r.get(f"pitching_ratings_talent_{k}"),
                )
                for k, label in PIT_TOOLS
            ]
            pairs.append(("stamina", r.get("pitching_ratings_misc_stamina"), None))
        return [
            {"tool": name, "now": int(number(now)), "ceiling": int(number(ceil)) or None}
            for name, now, ceil in pairs
            if number(now) > 0
        ]

    def summary(self, grid):
        """'Elite plate discipline and defense at LF; plus contact; weak power. Still growing: ...'"""
        main = [g for g in grid if g["tool"] != "stamina"]
        parts = []
        for grade, test in (("elite", lambda v: v >= 8), ("plus", lambda v: v == 7)):
            tools = [g["tool"] for g in main if test(g["now"])]
            if tools:
                parts.append(f"{grade} {join(tools)}")
        if not parts:
            best = max(main, key=lambda g: g["now"], default=None)
            if best:
                parts.append(f"best tool: {word(best['now'])} {best['tool']} ({best['now']}/10)")
        weak = [g["tool"] for g in main if g["now"] <= 3]
        if weak:
            parts.append(f"weak {join(weak)}")
        text = sentence("; ".join(parts) + ".") if parts else "No standout tools."
        growing = [g for g in main if g["ceiling"] and g["ceiling"] - g["now"] >= 2]
        if growing:
            g = max(growing, key=lambda g: g["ceiling"] - g["now"])
            text += f" Still growing: {g['tool']} {g['now']} now, {g['ceiling']} ceiling."
        return text

    def history(self, p):
        """This year (every level he played, with league rank) and the two seasons before."""
        rows, _ = self.desk.statistics(p)
        lines = []
        key, floor = ("outs", 15) if p["kind"] == "pit" else ("pa", 30)
        for r in rows:
            if r["year"] < self.d.year - 2 or number(r.get(key)) < floor:
                continue
            lines.append(
                {
                    "year": r["year"],
                    "level": LEVELS.get(r["level"], r["league"]),
                    "line": stat_text(p, r),
                }
            )
        return lines[:5]

    def fenway(self, p):
        """How his profile plays in our park, in plain words, from Fenway's own factors. The
        verdict comes from the same notable tools the note cites."""
        h = self.home
        name = h.get("name") or "our park"
        doubles = number(h.get("d"), 1)
        triples = number(h.get("t"), 1)
        if p["kind"] == "pit":
            r = self.d.ratings["players_pitching"].get(p["id"], {})
            movement = number(r.get("pitching_ratings_overall_movement"))
            if movement >= 6:
                return {
                    "verdict": "plays up",
                    "note": f"His {word(movement)} movement ({int(movement)}/10) keeps the ball down, "
                    f"which matters in a park that adds {doubles - 1:+.0%} doubles.",
                }
            if movement <= 4:
                return {
                    "verdict": "plays down",
                    "note": f"Fringe movement ({int(movement)}/10) means fly-ball contact, and {name} adds "
                    f"{doubles - 1:+.0%} doubles off the wall.",
                }
            return {
                "verdict": "neutral",
                "note": f"{name} is close to neutral for a pitcher like him.",
            }
        r = self.d.ratings["players_batting"].get(p["id"], {})
        gap = number(r.get("batting_ratings_overall_gap"))
        power = number(r.get("batting_ratings_overall_power"))
        side, factor = {
            "L": ("lefties", number(h.get("hr_l"), 1)),
            "R": ("righties", number(h.get("hr_r"), 1)),
        }.get(p["bats"], ("switch hitters", number(h.get("hr"), 1)))
        ups, downs = [], []
        if gap >= 6 and doubles > 1.03:
            ups.append(
                f"his {word(gap)} gap power ({int(gap)}/10) plays up: {name} adds {doubles - 1:+.0%} doubles"
            )
        if power >= 6 and factor < 0.99:
            downs.append(
                f"his home-run power ({int(power)}/10) plays down: {factor - 1:+.0%} homers for {side} here"
            )
        elif power >= 6 and factor > 1.01:
            ups.append(
                f"his home-run power ({int(power)}/10) plays up: {factor - 1:+.0%} homers for {side} here"
            )
        if not ups and not downs:
            return {
                "verdict": "neutral",
                "note": f"{name} doesn't change much for a hitter with his profile.",
            }
        lift = (
            4 * (doubles - 1) * gap / 10
            + 2 * (triples - 1) * gap / 10
            + 4 * (factor - 1) * power / 10
        )
        verdict = (
            "plays up"
            if not downs
            else "plays down" if not ups else "mostly plays up" if lift > 0 else "mostly plays down"
        )
        return {"verdict": verdict, "note": sentence("; ".join(ups + downs)) + "."}

    def current_job(self, p):
        r = self.m.roster
        for x in r["lineup"]:
            if x["player"] and x["player"]["id"] == p["id"]:
                return f"our everyday {x['position']}"
        for x in r["rotation"]:
            if x["player"] and x["player"]["id"] == p["id"]:
                return f"our #{x['slot']} starter"
        if any(x["player"] and x["player"]["id"] == p["id"] for x in r["bullpen"]):
            return "in our bullpen"
        if any(b["id"] == p["id"] for b in r["bench"]):
            return "on our bench"
        return None

    def team_fit(self, p):
        if p["free_agent"] and p["draft_eligible"]:
            return {
                "role": "Draft prospect",
                "line": "Draft-eligible amateur: no role yet.",
                "gain": 0.0,
            }
        ours = (p["organization_id"] or p["team_id"]) == self.d.team
        if ours and p["team_id"] == self.d.team and p["active"]:
            job = self.current_job(p)
            return {
                "role": "Ours",
                "line": f"He's {job}." if job else "He's on our active roster.",
                "gain": 0.0,
            }
        starts, share, line = job_read(self.d, self.e, p)
        _, their_rate = incumbent(self.d, self.e, p)
        gain = self.e.current_rate(p) - their_rate if starts else 0.0
        role = "Starts for us" if starts else "Splits time" if share >= 0.5 else "Depth"
        return {"role": role, "line": line, "gain": round(gain, 1)}

    def money(self, p):
        v = self.e.player(p)
        ours = (p["organization_id"] or p["team_id"]) == self.d.team
        if p["free_agent"]:
            return {
                "label": "Free agent",
                "line": f"Free agent: worth about {dollars(v['asking_value'])} a year to sign.",
                "value": v["asking_value"],
            }
        if ours:
            return {"label": "Ours", "line": v["summary"], "value": v["value"]}
        return {
            "label": "Trade value",
            "line": f"Would cost about {dollars(max(v['value'], 0))} in trade value. {v['summary']}",
            "value": v["value"],
        }

    def development(self, p):
        oa, pot = self.e.rating(p)
        chance = self.e.chance_develops(p)
        ahead = self.e.forecast(p, self.d.year + 3)
        path = ", ".join(f"{s['year']}: {s['war']:.1f}" for s in ahead[1:4])
        if chance >= 1 and int(p["age"]) >= 30:
            stage = f"Age {p['age']}: past his peak; expect a gradual decline"
        elif chance >= 1:
            stage = f"Age {p['age']}: at his peak"
        else:
            stage = f"Age {p['age']}: {oa / pot:.0%} of his ceiling now, {chance:.0%} chance he gets there"
        return {"stage": stage, "path": f"Projected wins a season: {path}." if path else ""}

    # ---- the report ------------------------------------------------------------------------

    def report(self, pid):
        p = self.d.by_id.get(int(pid))
        if not p:
            raise ValueError("That player isn't in this export.")
        grid = self.tool_grid(p)
        fit = self.team_fit(p)
        park = self.fenway(p)
        money = self.money(p)
        return {
            "id": p["id"],
            "name": p["name"],
            "age": p["age"],
            "kind": p["kind"],
            "position": p["position"] if p["kind"] == "bat" else self.e.role(p).upper(),
            "bats_throws": f"{p['bats']}/{p['throws']}",
            "where": "Free agent" if p["free_agent"] else self.m.where(p),
            "verdict": self.verdict(p, fit, park, money),
            "summary": self.summary(grid),
            "tools": grid,
            "this_year": self.m.line(p),
            "history": self.history(p),
            "development": self.development(p),
            "fenway": park,
            "fit": fit,
            "money": money,
            "wins": round(self.e.current_rate(p), 1),
            "injured": p["injured"] or p["on_dl"],
            "day_to_day": p.get("day_to_day"),
        }

    def verdict(self, p, fit, park, money):
        bits = []
        if fit["role"] == "Starts for us":
            bits.append(f"would start for us (+{fit['gain']:.1f} wins a season)")
        elif fit["role"] == "Splits time":
            bits.append("would split time for us")
        elif fit["role"] == "Ours":
            bits.append(fit["line"].rstrip(".").replace("He's", "he's"))
        elif fit["role"] == "Draft prospect":
            bits.append("a draft prospect")
        else:
            bits.append("would be depth for us")
        if park["verdict"] != "neutral":
            bits.append(f"his game {park['verdict']} at Fenway")
        if money["label"] == "Trade value" and money["value"] > 0:
            bits.append(f"costs about {dollars(money['value'])} in trade value")
        elif money["label"] == "Free agent":
            bits.append(f"about {dollars(money['value'])} a year on the market")
        if p["injured"] or p["on_dl"]:
            bits.append("hurt right now")
        good = fit["role"] in ("Starts for us", "Ours") or (
            fit["role"] == "Splits time" and "up" in park["verdict"]
        )
        head = (
            "Fits" if good else "Doesn't fit right now" if fit["role"] == "Depth" else "Partial fit"
        )
        return f"{head}: {', '.join(bits)}."

    def compare(self, ids):
        ids = [int(i) for i in ids][:6]
        if not ids:
            raise ValueError("Pick at least one player to scout.")
        return {"reports": [self.report(i) for i in ids]}


def scout_players(office, ids):
    return Scout(office).compare(ids)
