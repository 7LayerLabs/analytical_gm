"""Versioned GM preferences and evidence-based presentation. Never writes to OOTP."""

import bisect, collections, math, os, secrets, threading
from datetime import datetime, timezone
from analytics import number, batting, pitching, POSITIONS
from storage import DATA, connect, records, read_json, write_json, snapshots

LOCK = threading.RLock()
IDENTITIES = [
    {
        "id": "traditional",
        "name": "Old-school Baseball",
        "tag": "Contact, speed and positional defense",
        "priorities": [
            "Speed near the top of the order",
            "Strongest bat third, power fourth",
            "Contact, defense and purposeful baserunning",
        ],
        "tradeoff": "Traditional lineup roles are a preference, not a claim of optimized runs.",
    },
    {
        "id": "moneyball",
        "name": "Original Moneyball",
        "tag": "Buy overlooked on-base ability",
        "priorities": [
            "Affordable OBP and plate discipline",
            "Patient hitters over reputation",
            "Protect payroll flexibility",
        ],
        "tradeoff": "An OBP edge is a hypothesis until acquisition prices confirm it. Defense and pitching still matter.",
        "history": "Inspired by Oakland’s late-1990s approach and the 2002 club made famous by Moneyball.",
    },
    {
        "id": "edgehunter",
        "name": "Edgehunter",
        "tag": "Find the next mispriced skill",
        "priorities": [
            "Test overlooked skills against this league",
            "Look for platoon, defense and park-fit opportunities",
            "Compare price with our internal alternative",
        ],
        "tradeoff": "A high rating alone is not an undervalued asset. Salary is only part of acquisition cost.",
    },
    {
        "id": "farm",
        "name": "Farm Factory",
        "tag": "Develop a renewable contender",
        "priorities": [
            "Internal depth and player development",
            "Acquire controllable upside",
            "Replace expensive production before it leaves",
        ],
        "tradeoff": "Development and prospect returns remain uncertain; avoid promoting talent without a role.",
    },
    {
        "id": "powerhouse",
        "name": "Big-market Powerhouse",
        "tag": "Turn resources into elite talent",
        "priorities": [
            "Premium impact players",
            "Deep pitching and quality backups",
            "Use spending capacity to preserve prospects",
        ],
        "tradeoff": "Long commitments can constrain future windows; confirm actual available funds.",
    },
    {
        "id": "trader",
        "name": "Trade Architect",
        "tag": "Rebuild the roster through deals",
        "priorities": [
            "Trade from organizational strength",
            "Buy near-term upgrades with clear roles",
            "Balance packages against future contention",
        ],
        "tradeoff": "Do not mistake another club’s best player for an available or affordable target.",
    },
    {
        "id": "sustainable",
        "name": "Sustainable Contender",
        "tag": "Compete this year and next",
        "priorities": [
            "Layer affordable depth around a core",
            "Manage arbitration and option decisions early",
            "Avoid sacrificing the next window for a small upgrade",
        ],
        "tradeoff": "May pass on expensive short-term upside.",
    },
    {
        "id": "homegrown",
        "name": "Homegrown Core",
        "tag": "Build continuity from within",
        "priorities": [
            "Develop and extend foundational players",
            "Reserve clear paths to MLB playing time",
            "Add outside help around the core",
        ],
        "tradeoff": "Attachment cannot substitute for evaluating performance and development.",
    },
    {
        "id": "stars",
        "name": "Stars & Support",
        "tag": "Elite pillars, dependable depth",
        "priorities": [
            "Secure difference-makers",
            "Find complementary platoon and defensive roles",
            "Protect against a top-heavy roster",
        ],
        "tradeoff": "A weak bench or rotation back end can erase advantages at the top.",
    },
    {
        "id": "opportunity",
        "name": "Opportunity Buyer",
        "tag": "Stay ready when prices drop",
        "priorities": [
            "Preserve budget and roster flexibility",
            "Monitor rebound candidates",
            "Buy meaningful upgrades when cost falls",
        ],
        "tradeoff": "Waiting can leave immediate needs uncovered.",
    },
]
MODES = ["Win now", "All in", "Hold & evaluate", "Retool", "Selective sell", "Rebuild"]
SKILLS = [
    "On-base ability",
    "Power",
    "Contact",
    "Speed",
    "Defense up the middle",
    "Pitching depth",
    "Strikeouts",
    "Control",
    "Durability",
    "Platoon versatility",
]
GLOSSARY = [
    (
        "OBP",
        "How often a hitter reaches base through a hit, walk or hit-by-pitch. More opportunities help the lineup; compare with the current league and acquisition price.",
    ),
    (
        "OPS",
        "OBP + slugging percentage. A useful summary of offense, but it weighs two different scales equally and does not include defense, baserunning or park context. Our OPS index is not OPS+.",
    ),
    (
        "AVG",
        "Hits divided by at-bats. Still useful for describing hits, but misses walks and extra-base value. A low-average hitter can be valuable if he reaches base and hits for power.",
    ),
    (
        "SLG",
        "Total bases divided by at-bats. Captures extra-base production; does not count walks.",
    ),
    ("ISO", "SLG minus AVG. Describes extra-base power per at-bat."),
    (
        "BABIP",
        "Batting average on balls in play, excluding home runs. Depends on contact quality, speed, defense, park and variation. A change is not automatically luck.",
    ),
    (
        "K%",
        "Strikeouts divided by plate appearances (hitters) or batters faced (pitchers). Lower helps hitters put balls in play; higher usually helps pitchers.",
    ),
    (
        "BB%",
        "Walks divided by plate appearances or batters faced. Hitter walks help OBP; pitcher walks add baserunners.",
    ),
    (
        "K−BB%",
        "Pitcher strikeout rate minus walk rate. Useful skill summary; still needs home-run, workload and contact context.",
    ),
    (
        "ERA",
        "Earned runs per nine innings. Describes what happened; defense, sequencing and park influence it.",
    ),
    (
        "FIP",
        "An estimate based on home runs, walks, hit batters and strikeouts. Uses the prior MLB season constant here. Does not describe all run prevention or directly simulate OOTP.",
    ),
    (
        "WHIP",
        "Walks plus hits per inning. Describes baserunners without weighting how damaging each was.",
    ),
    (
        "WAR",
        "Wins above replacement, as exported by OOTP. A useful broad value estimate; not a guaranteed future result or a literal trade price.",
    ),
    (
        "RBI",
        "Runs driven in. Opportunity-dependent: teammates reaching base and lineup position matter. Solo homers give only one RBI, so 40 HR and 80 RBI can coexist without poor hitting.",
    ),
    (
        "Gap power",
        "OOTP ability associated with doubles/triples. Your park’s exported factors show whether it favors them, but a 10 gap rating does not guarantee a specific extra-base total.",
    ),
    (
        "Contact",
        "OOTP’s composite contact ability. We show BABIP and avoid-K separately, but do not add them again to our contact component.",
    ),
    (
        "Percentile",
        "Percentage below a value plus half the percentage tied with it. Rounded ratings create many ties: a 5 is not automatically the median.",
    ),
    (
        "Department grade",
        "A 1–10 preference score: 65% current ratings and 35% conservative MLB rate forecast, with a maximum ±0.4 park-fit adjustment. It is not a calibrated WAR or win prediction.",
    ),
    (
        "Park factor",
        "1.000 is neutral. Factors describe the park’s influence in OOTP. Schedule-weighted factors use actual regular-season venues, not an assumed division share.",
    ),
    (
        "Service time",
        "Exported MLB service days and years. A full service year is 172 days in this save’s context. Arbitration eligibility, free agency and Super Two are different questions; check current game rules before a move.",
    ),
    (
        "Options",
        "Contract options and roster option years are different. Scheduled contract option salaries remain conditional; roster option availability requires checking the game.",
    ),
    (
        "Evidence",
        "Forecasts blend the last three completed MLB seasons with a league-average prior. Limited history increases shrinkage; minor-league numbers are displayed without invented MLB conversion.",
    ),
]


def percentile(values, value):
    values = sorted(values)
    n = len(values)
    if not n:
        return {"percentile": None, "lower": 0, "tied": 0, "higher": 0, "n": 0}
    lo = bisect.bisect_left(values, value)
    hi = bisect.bisect_right(values, value)
    return {
        "percentile": round(100 * (lo + (hi - lo) / 2) / n, 1),
        "lower": round(100 * lo / n, 1),
        "tied": round(100 * (hi - lo) / n, 1),
        "higher": round(100 * (n - hi) / n, 1),
        "n": n,
    }


def assignment(scores):
    """Rectangular Hungarian assignment: maximize total fit, one player per position."""
    n = len(scores)
    if not n:
        return []
    m = len(scores[0])
    u = [0] * (n + 1)
    v = [0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minimum = [math.inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = math.inf
            j1 = 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = -scores[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minimum[j]:
                        minimum[j] = cur
                        way[j] = j0
                    if minimum[j] < delta:
                        delta = minimum[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    result = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            result[p[j] - 1] = j - 1
    return result


def default_state(d):
    return {
        "blueprint": {
            "seasons": {
                str(d.year): "Win now",
                str(d.year + 1): "Win now",
                str(d.year + 2): "Hold & evaluate",
            },
            "goal": "Make the playoffs; build a club capable of winning the World Series",
            "identities": [],
            "philosophy": "Blended",
            "playing_notes": "",
            "style_source": [],
            "style_overrides": [],
            "skills": {s: "Preferred" for s in SKILLS},
            "boundaries": "Protect next season’s contender; assess cost before trading long-term core players.",
            "reason": "Opening team plan",
            "cadence": "Weekly",
        },
        "versions": [],
        "locks": [],
        "watchlist": [],
        "decisions": [],
        "checkpoints": [],
        "owner_goals": {},
        "owner_goal_history": [],
    }


def state_path(d):
    """Blueprint, locks, watchlist and saved decisions: one file per save and club, so Boston in
    two different leagues never shares locks on the wrong players."""
    source = d.manifest.get("source_id") or "save"
    path = DATA / f"frontoffice-{source}-team{d.team}-league{d.league}.json"
    legacy = DATA / f"frontoffice-team{d.team}-league{d.league}.json"
    if not path.exists() and legacy.exists():
        # Written before leagues were separated; it belongs to the first save that opens it.
        os.replace(legacy, path)
    return path


def office_state(d):
    base = default_state(d)
    saved = read_json(state_path(d), base)
    saved = {**base, **saved}
    saved["blueprint"] = {**base["blueprint"], **saved["blueprint"]}
    return saved


def stamp(d):
    return {
        "id": secrets.token_hex(8),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": d.sid,
        "game_date": str(d.manifest["game_date"]),
    }


def save(d, body):
    action = body.get("action")
    s = office_state(d)
    with LOCK:
        s = office_state(d)
        if action == "blueprint":
            b = body["blueprint"]
            valid_ids = {i["id"] for i in IDENTITIES}
            if any(v not in MODES for v in b.get("seasons", {}).values()):
                raise ValueError("Choose a supported seasonal direction.")
            if any(i not in valid_ids for i in b.get("identities", [])):
                raise ValueError("Unknown identity.")
            if b.get("philosophy") not in ["Analytics-led", "Traditional", "Blended"]:
                raise ValueError("Unknown playing philosophy.")
            if not str(b.get("reason", "")).strip():
                raise ValueError("Explain why you are saving this version.")
            b = {k: b.get(k, s["blueprint"].get(k)) for k in s["blueprint"]}
            valid_style = {"philosophy", "playing_notes", *("skill-" + k for k in SKILLS)}
            if any(k not in valid_style for k in b["style_overrides"]):
                raise ValueError("Unknown customized style field.")
            b["style_source"] = list(b["identities"])
            b["playing_notes"] = str(b["playing_notes"])[:10000]
            for value in b["skills"].values():
                if value not in ["Essential", "Preferred", "Optional"]:
                    raise ValueError("Invalid skill priority.")
            if len(b["identities"]) != len(set(b["identities"])):
                raise ValueError("Choose each identity once.")
            s["versions"].insert(0, {**stamp(d), "before": s["blueprint"], "blueprint": b})
            s["blueprint"] = b
        elif action == "owner-goals":
            from owner_goals import validate_goals, capture_baseline

            year, entry = validate_goals(body)
            before = s["owner_goals"].get(str(year), {})
            entry["baseline"] = before.get("baseline") or (
                capture_baseline(Office(d)) if year == d.year else {}
            )
            entry.update(stamp(d))
            s["owner_goal_history"].insert(
                0, {**stamp(d), "year": year, "before": before, "after": entry}
            )
            s["owner_goals"][str(year)] = entry
        elif action == "lock":
            pid = int(body["player_id"])
            p = d.by_id.get(pid)
            if not p or p not in d.own():
                raise ValueError("Lock a player in your organization.")
            scope = body.get("scope", "roster")
            hand = body.get("hand", "both")
            pos = body.get("position", "")
            slot = int(body.get("slot") or 0)
            if scope not in ["roster", "lineup", "rotation", "bullpen", "trade"]:
                raise ValueError("Invalid lock type.")
            if hand not in ["both", "vsr", "vsl"] or pos not in ["", *POSITIONS.values()]:
                raise ValueError("Invalid lock placement.")
            if not 0 <= slot <= 9 or (scope == "rotation" and slot > 5):
                raise ValueError("Invalid lineup or rotation slot.")
            if scope in ["rotation", "bullpen"] and p["kind"] != "pit":
                raise ValueError("Pitching roles require a pitcher.")
            if scope == "lineup" and p["kind"] != "bat":
                raise ValueError("A batting lineup lock requires a hitter.")
            if scope == "lineup" and pos == "P":
                raise ValueError("Choose a batting position.")
            lock = {
                **stamp(d),
                "player_id": pid,
                "name": p["name"],
                "scope": scope,
                "hand": hand,
                "position": pos,
                "slot": slot,
                "reason": str(body.get("reason", ""))[:2000],
            }
            s["locks"] = [
                l
                for l in s["locks"]
                if not (l["player_id"] == pid and l["scope"] == scope and l["hand"] == hand)
            ]
            s["locks"].append(lock)
        elif action == "unlock":
            s["locks"] = [l for l in s["locks"] if l["id"] != body["id"]]
        elif action == "watch":
            pid = int(body["player_id"])
            p = d.by_id.get(pid)
            if not p:
                raise ValueError("Unknown player.")
            s["watchlist"] = [x for x in s["watchlist"] if x["player_id"] != pid]
            s["watchlist"].insert(
                0,
                {
                    **stamp(d),
                    "player_id": pid,
                    "name": p["name"],
                    "reason": str(body.get("reason", ""))[:2000],
                    "review": str(body.get("review", "Next export"))[:150],
                },
            )
        elif action == "unwatch":
            s["watchlist"] = [x for x in s["watchlist"] if x["id"] != body["id"]]
        elif action == "checkpoint":
            label = body.get("label")
            if label not in ["Opening season", "All-Star break", "End of season"]:
                raise ValueError("Invalid checkpoint.")
            s["checkpoints"].insert(0, {**stamp(d), "label": label, "year": d.year})
        elif action == "decision":
            case = evaluate(d, body.get("case", {}))
            s["decisions"].insert(
                0, {**stamp(d), "status": "Exploring", "case": body.get("case", {}), "report": case}
            )
        elif action == "decision-status":
            if body["status"] not in ["Exploring", "Chosen", "Applied in OOTP", "Revisit"]:
                raise ValueError("Invalid decision status.")
            for x in s["decisions"]:
                if x["id"] == body["id"]:
                    x.setdefault("history", []).append(
                        {**stamp(d), "before": x["status"], "after": body["status"]}
                    )
                    x["status"] = body["status"]
        else:
            raise ValueError("Unknown department action.")
        write_json(state_path(d), s)
    return s


class Office:
    def __init__(self, d):
        self.d = d
        self.state = office_state(d)
        self.b = self.state["blueprint"]
        self.cohorts = {}
        self.parks = self.schedule()
        self.cards = {}
        for p in d.profiles:
            if p["league_id"] == d.league:
                self.cohorts.setdefault(self.role(p), []).append(p)

    def role(self, p):
        if p["kind"] == "bat":
            return "Hitters"
        r = self.d.ratings["players_pitching"].get(p["id"], {})
        h = self.d.hist["pit"].get(p["id"], [])
        last = max(h, key=lambda x: x["year"]) if h else {}
        return (
            "Starters"
            if number(r.get("pitching_ratings_misc_stamina")) >= 5
            and (not last or number(last.get("gs")) >= number(last.get("g")) * 0.5)
            else "Relievers"
        )

    def schedule(self):
        d = self.d
        t = d.teams[d.team]
        counts = collections.Counter()
        groups = collections.Counter()
        with connect(d.sid) as c:
            games = records(
                c,
                "select home_team,away_team from games where league_id=? and game_type=0 and year(date)=? and (home_team=? or away_team=?)",
                [d.league, d.year, d.team, d.team],
            )
        for g in games:
            home = d.teams.get(g["home_team"], {})
            pid = home.get("park_id")
            counts[pid] += 1
            same = all(home.get(k) == t.get(k) for k in ["division_id", "sub_league_id"])
            groups[
                "Home" if g["home_team"] == d.team else "Division road" if same else "Other road"
            ] += 1
        if not games:
            counts[t.get("park_id")] = 1
            groups["Home only — schedule unavailable"] = 1
        total = sum(counts.values())
        keys = ["avg", "avg_l", "avg_r", "d", "t", "hr", "hr_l", "hr_r"]
        weighted = {
            k: round(
                sum(number(d.parks.get(pid, {}).get(k), 1) * n for pid, n in counts.items())
                / total,
                4,
            )
            for k in keys
        }
        return {
            "games": len(games),
            "groups": dict(groups),
            "factors": weighted,
            "home": d.parks.get(t.get("park_id"), {}),
            "venues": [
                {
                    "name": d.parks.get(pid, {}).get("name", "Unknown park"),
                    "games": n,
                    "weight": n / total,
                }
                for pid, n in counts.most_common()
            ],
        }

    def skill_specs(self, kind):
        return (
            [
                ("Contact", "contact"),
                ("Gap power", "gap"),
                ("Home-run power", "power"),
                ("Plate discipline", "eye"),
                ("Avoid strikeouts", "strikeouts"),
                ("BABIP ability", "babip"),
            ]
            if kind == "bat"
            else [
                ("Stuff", "stuff"),
                ("Movement", "movement"),
                ("Control", "control"),
                ("Home-run prevention", "hra"),
                ("BABIP prevention", "pbabip"),
            ]
        )

    def skills(self, p):
        d = self.d
        kind = p["kind"]
        table = "players_batting" if kind == "bat" else "players_pitching"
        prefix = "batting_ratings_" if kind == "bat" else "pitching_ratings_"
        r = d.ratings[table].get(p["id"], {})
        cohort = self.cohorts.get(self.role(p), [])
        out = []
        for label, key in self.skill_specs(kind):
            value = number(r.get(prefix + "overall_" + key))
            vals = [
                number(d.ratings[table].get(q["id"], {}).get(prefix + "overall_" + key))
                for q in cohort
            ]
            out.append(
                {
                    "label": label,
                    "key": key,
                    "current": value,
                    "potential": r.get(prefix + "talent_" + key),
                    "vsr": r.get(prefix + "vsr_" + key),
                    "vsl": r.get(prefix + "vsl_" + key),
                    "mean": round(sum(vals) / len(vals), 2) if vals else None,
                    **percentile(vals, value),
                    "cohort": self.role(p),
                }
            )
        return out

    def card(self, p):
        if p["id"] in self.cards:
            return self.cards[p["id"]]
        d = self.d
        kind = p["kind"]
        r = d.ratings["players_batting" if kind == "bat" else "players_pitching"].get(p["id"], {})
        prefix = "batting_ratings_overall_" if kind == "bat" else "pitching_ratings_overall_"
        weights = (
            {"contact": 0.30, "power": 0.35, "eye": 0.25, "strikeouts": 0.10}
            if kind == "bat"
            else {"stuff": 0.40, "movement": 0.30, "control": 0.30}
        )
        ids = self.b["identities"]
        skills = self.b["skills"]
        if kind == "bat" and "moneyball" in ids:
            weights = {"contact": 0.25, "power": 0.20, "eye": 0.45, "strikeouts": 0.10}
        if kind == "bat":
            for label, key in [
                ("On-base ability", "eye"),
                ("Contact", "contact"),
                ("Power", "power"),
            ]:
                if skills.get(label) == "Essential":
                    weights[key] += 0.12
        else:
            for label, key in [("Strikeouts", "stuff"), ("Control", "control")]:
                if skills.get(label) == "Essential":
                    weights[key] += 0.12
        rating = sum(number(r.get(prefix + k)) * w for k, w in weights.items()) / sum(
            weights.values()
        )
        statgrade = max(1, min(10, 5 + (number(p["score"], 100) - 100) / 15))
        fit = self.park_fit(p)
        grade = round(max(1, min(10, 0.65 * rating + 0.35 * statgrade + fit["adjustment"])), 1)
        proj = p["projection"]
        scheduled = self.contract_schedule(p)
        end = max((r["year"] for r in scheduled), default=None)
        desc = (
            "above-average"
            if p["score"] >= 110
            else "below-average" if p["score"] < 90 else "around league-average"
        )
        if kind == "bat":
            best = max(self.skill_specs(kind), key=lambda x: number(r.get(prefix + x[1])))
            lead = (
                f"Projects as an {desc} hitter."
                if desc == "above-average"
                else (
                    "Projects around league average as a hitter."
                    if desc == "around league-average"
                    else f"Projects as a {desc} hitter."
                )
            )
            detail = (
                "His ability to reach base is the strongest part of his offensive profile. "
                if best[1] == "eye"
                else f"{best[0]} is the strongest part of his offensive ratings. "
            )
        else:
            lead = f"Projects for {desc} strikeout, walk and home-run performance."
            detail = f"{self.role(p)[:-1]} profile; judge workload and overall run prevention separately. "
        if not proj.get("observed_exposure"):
            lead = f"Current ratings suggest {'above-average' if rating>=6.5 else 'developing' if rating<4 else 'usable'} {'pitching' if kind=='pit' else 'hitting'} ability; MLB translation remains uncertain."
            detail = "No completed MLB history is available. The statistical forecast is the league baseline, not an individualized MLB projection. Review actual minor-league performance and playing time."
        else:
            detail += (
                f"The forecast is conservative because his prior MLB sample is only {int(proj['observed_exposure']):,} {'batters faced' if kind=='pit' else 'plate appearances'}."
                if proj.get("evidence") != "Established"
                else "The forecast uses his last three completed MLB seasons, balanced with the league baseline."
            )
        speed = number(d.ratings["players_batting"].get(p["id"], {}).get("running_ratings_speed"))
        cdata = {
            **p,
            "grade": grade,
            "rating_component": round(rating, 2),
            "stat_component": round(statgrade, 2),
            "grade_weights": weights,
            "summary": lead,
            "detail": detail,
            "fit": fit,
            "speed": speed,
            "end_year": end,
            "years_left": max(0, end - d.year + 1) if end else 0,
            "scheduled_total": sum(p["salaries"].values()),
            "locks": [x for x in self.state["locks"] if x["player_id"] == p["id"]],
        }
        self.cards[p["id"]] = cdata
        return cdata

    def park_fit(self, p):
        d = self.d
        r = d.ratings["players_batting" if p["kind"] == "bat" else "players_pitching"].get(
            p["id"], {}
        )
        f = self.parks["factors"]
        home = self.parks["home"]
        notes = []
        if p["kind"] == "bat":
            gap = number(r.get("batting_ratings_overall_gap"))
            power = number(r.get("batting_ratings_overall_power"))
            hr = f["hr_l"] if p["bats"] == "L" else f["hr_r"] if p["bats"] == "R" else f["hr"]
            adjust = (
                4 * (f["d"] - 1) * gap / 10
                + 2 * (f["t"] - 1) * gap / 10
                + 4 * (hr - 1) * power / 10
            )
            notes.append(
                f"Gap power {gap:g}/10 meets {home.get('name','home park')} doubles factor {number(home.get('d'),1):.3f} and triples {number(home.get('t'),1):.3f}."
            )
            notes.append(
                f"Schedule-weighted home-run factor {hr:.3f} for his batting side; switch hitters use the overall factor because opponent handedness is not known."
            )
        else:
            adjust = -4 * (f["hr"] - 1)
            notes.append(
                f"Schedule-weighted HR factor {f['hr']:.3f}; defense and batted-ball mix still influence results."
            )
        return {
            "adjustment": round(max(-0.4, min(0.4, adjust)), 3),
            "notes": notes,
            "home": home.get("name"),
            "weighted": f,
            "label": "Preference fit; not a park-adjusted forecast",
        }

    def candidates(self, scope="organization", q="", kind="", position=""):
        d = self.d
        ps = (
            d.own()
            if scope == "organization"
            else (
                d.active()
                if scope == "active"
                else (
                    [p for p in d.profiles if p["free_agent"] and not p["draft_eligible"]]
                    if scope == "free"
                    else (
                        [p for p in d.profiles if p["league_id"] == d.league]
                        if scope == "mlb"
                        else (
                            [p for p in d.profiles if p["draft_eligible"]]
                            if scope == "draft"
                            else d.profiles
                        )
                    )
                )
            )
        )
        ps = [
            p
            for p in ps
            if q.lower() in p["name"].lower()
            and (not kind or p["kind"] == kind)
            and (not position or p["position"] == position)
        ]
        return sorted([self.card(p) for p in ps], key=lambda x: x["grade"], reverse=True)

    def roster(self, hand="vsr", internal=False):
        if hand not in ["vsr", "vsl"]:
            raise ValueError("Invalid handedness.")
        d = self.d
        pool = [
            p
            for p in (d.own() if internal else d.active())
            if not p["injured"] and not p["on_dl"] and not p["dfa"] and not p["on_waivers"]
        ]
        hitters = [p for p in pool if p["kind"] == "bat"]
        warnings = []
        used = set()
        placements = {}
        locks = self.state["locks"]

        def score(p):
            r = d.ratings["players_batting"].get(p["id"], {})
            w = self.card(p)["grade_weights"]
            return (
                sum(number(r.get("batting_ratings_" + hand + "_" + k)) * v for k, v in w.items())
                / sum(w.values())
                + 0.08 * self.card(p)["grade"]
            )

        relevant = [l for l in locks if l["scope"] == "lineup" and l["hand"] in ["both", hand]]
        for l in relevant:
            p = d.by_id.get(l["player_id"])
            pos = l["position"] or p["position"]
            if pos not in ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]:
                warnings.append(f"{p['name']}: choose a batting position for this lock.")
                continue
            if p not in hitters:
                warnings.append(
                    f"Locked {p['name']} is unavailable in this pool. Lock retained; resolve eligibility before using this lineup."
                )
                continue
            code = next(k for k, v in POSITIONS.items() if v == pos)
            if (
                pos != "DH"
                and number(
                    d.ratings["players_fielding"].get(p["id"], {}).get(f"fielding_rating_pos{code}")
                )
                < 4
            ):
                warnings.append(
                    f"{p['name']} is locked at {pos} with position rating below 4; defensive risk."
                )
            if pos in placements or p["id"] in used:
                warnings.append(f"Conflicting lock for {p['name']} at {pos}; resolve the conflict.")
                continue
            placements[pos] = {
                "position": pos,
                "player": self.card(p),
                "locked": True,
                "slot": l["slot"],
            }
            used.add(p["id"])
        codes = [c for c in [2, 6, 8, 4, 5, 9, 7, 3, 10] if POSITIONS[c] not in placements]
        available = [p for p in hitters if p["id"] not in used]
        speed_weight = 0.12 if self.b["skills"].get("Speed") == "Essential" else 0.06
        defense_weight = (
            0.30 if self.b["skills"].get("Defense up the middle") == "Essential" else 0.18
        )
        matrix = []
        for code in codes:
            vals = []
            for p in available:
                defense = number(
                    d.ratings["players_fielding"].get(p["id"], {}).get(f"fielding_rating_pos{code}")
                )
                value = (
                    score(p)
                    + speed_weight * self.card(p)["speed"]
                    + defense_weight * defense * (1.25 if code in [2, 4, 6, 8] else 1)
                )
                vals.append(value if code == 10 or defense >= 4 else -1000)
            matrix.append(vals + [0] * len(codes))
        for code, j in zip(codes, assignment(matrix)):
            if j < len(available) and matrix[codes.index(code)][j] > 0:
                best = available[j]
                used.add(best["id"])
                placements[POSITIONS[code]] = {
                    "position": POSITIONS[code],
                    "player": self.card(best),
                    "locked": False,
                    "slot": 0,
                }
        ordered = sorted(
            placements.values(), key=lambda x: score(d.by_id[x["player"]["id"]]), reverse=True
        )
        if ordered:
            if self.b["philosophy"] == "Traditional":
                fast = max(ordered, key=lambda x: x["player"]["speed"])
                ordered.remove(fast)
                ordered.insert(0, fast)
                if len(ordered) > 3:
                    best = max(ordered[1:], key=lambda x: score(d.by_id[x["player"]["id"]]))
                    ordered.remove(best)
                    ordered.insert(2, best)
                if len(ordered) > 4:
                    power = max(
                        [x for i, x in enumerate(ordered) if i not in [0, 2]],
                        key=lambda x: number(
                            d.ratings["players_batting"][x["player"]["id"]].get(
                                "batting_ratings_" + hand + "_power"
                            )
                        ),
                    )
                    ordered.remove(power)
                    ordered.insert(3, power)
            else:
                lead = max(
                    ordered[:5],
                    key=lambda x: number(
                        d.ratings["players_batting"][x["player"]["id"]].get(
                            "batting_ratings_" + hand + "_eye"
                        )
                    ),
                )
                ordered.remove(lead)
                ordered.insert(0, lead)
        fixed = {}
        for x in ordered:
            if x["slot"]:
                if x["slot"] in fixed:
                    warnings.append(
                        "Two locks request the same batting slot; resolve before using the lineup."
                    )
                else:
                    fixed[x["slot"]] = x
        remaining = [x for x in ordered if x not in fixed.values()]
        lineup = []
        for n in range(1, 10):
            x = fixed.get(n) or (remaining.pop(0) if remaining else None)
            if x:
                lineup.append({**x, "slot": n})
        pitchers = [p for p in pool if p["kind"] == "pit"]
        rotation = []
        bullpen = []
        plocks = [l for l in locks if l["scope"] in ["rotation", "bullpen"]]
        lockedids = {l["player_id"] for l in plocks}
        for p in pitchers:
            item = {
                "player": self.card(p),
                "stamina": d.ratings["players_pitching"]
                .get(p["id"], {})
                .get("pitching_ratings_misc_stamina"),
                "locked": p["id"] in lockedids,
            }
            ls = [l for l in plocks if l["player_id"] == p["id"]]
            if len({l["scope"] for l in ls}) > 1:
                warnings.append(f"{p['name']} has conflicting rotation and bullpen locks.")
            item["slot"] = next((l["slot"] for l in ls if l["scope"] == "rotation"), 0)
            (
                rotation
                if any(l["scope"] == "rotation" for l in ls)
                or (not ls and self.role(p) == "Starters")
                else bullpen
            ).append(item)
        for l in plocks:
            if not any(p["id"] == l["player_id"] for p in pitchers):
                warnings.append(f"Locked {l['name']} is unavailable; pitching lock retained.")
        rotation.sort(key=lambda x: (x["locked"], x["player"]["grade"]), reverse=True)
        overflow = rotation[5:]
        rotation = rotation[:5]
        bullpen += overflow
        for x in overflow:
            if x["locked"]:
                warnings.append(
                    f"{x['player']['name']}: more than five rotation locks. Resolve this before using the plan."
                )
        pinned = {}
        free = []
        for x in rotation:
            if x["slot"]:
                if x["slot"] in pinned:
                    warnings.append("Rotation slot conflict; resolve before using this plan.")
                    free.append(x)
                else:
                    pinned[x["slot"]] = x
            else:
                free.append(x)
        rotation = [
            {
                **(pinned.get(i) or (free.pop(0) if free else {"player": None, "locked": False})),
                "slot": i,
            }
            for i in range(1, 6)
        ]
        rosterlocked = {l["player_id"] for l in locks if l["scope"] == "roster"}
        bullpen.sort(
            key=lambda x: (x["locked"] or x["player"]["id"] in rosterlocked, x["player"]["grade"]),
            reverse=True,
        )
        bullpen = bullpen[:8]
        bench = sorted(
            [p for p in hitters if p["id"] not in used],
            key=lambda p: (p["id"] in rosterlocked, self.card(p)["grade"]),
            reverse=True,
        )[:4]
        # Preserve a second usable catcher instead of filling every bench spot by bat grade.
        catchers = [
            p
            for p in hitters
            if number(d.ratings["players_fielding"].get(p["id"], {}).get("fielding_rating_pos2"))
            >= 4
        ]
        selected_bats = used | {p["id"] for p in bench}
        if sum(p["id"] in selected_bats for p in catchers) < 2:
            candidates = sorted(
                [p for p in catchers if p["id"] not in selected_bats],
                key=lambda p: self.card(p)["grade"],
                reverse=True,
            )
            replaceable = sorted(
                [p for p in bench if p["id"] not in rosterlocked and p not in catchers],
                key=lambda p: self.card(p)["grade"],
            )
            if candidates and replaceable:
                bench.remove(replaceable[0])
                bench.append(candidates[0])
            else:
                warnings.append(
                    "Backup catcher coverage is incomplete; resolve this before using the roster."
                )
        selectedids = (
            {x["player"]["id"] for x in lineup}
            | {x["player"]["id"] for x in rotation if x["player"]}
            | {x["player"]["id"] for x in bullpen}
            | {p["id"] for p in bench}
        )
        for l in locks:
            if (
                l["scope"] == "roster"
                and l["player_id"] not in selectedids
                and any(p["id"] == l["player_id"] for p in pool)
            ):
                warnings.append(
                    f"Roster lock for {l['name']} exceeds available role places. Resolve the conflict; lock remains binding."
                )
        for l in locks:
            if l["scope"] == "roster" and not any(p["id"] == l["player_id"] for p in pool):
                warnings.append(
                    f"Roster lock for {l['name']} requires an assignment or health review; retained as a required roster constraint."
                )
        from pitching_roles import pitching_recommendations

        pitching = pitching_recommendations(self, rotation, bullpen)
        grades = [x["player"]["grade"] if x["player"] else 0 for x in rotation]
        shape = (
            "Top-heavy rotation"
            if sum(grades[:2]) / 2 - sum(grades[2:]) / 3 >= 1.5
            else "Uneven rotation coverage" if 0 in grades else "Balanced rotation profile"
        )
        result = {
            "pitching_recommendations": pitching,
            "lineup": lineup,
            "rotation": rotation,
            "bullpen": bullpen,
            "bench": [self.card(p) for p in bench],
            "selected_count": len(selectedids),
            "warnings": warnings,
            "ready_for_review": not warnings,
            "shape": shape,
            "internal": internal,
            "hand": hand,
            "unfilled": [
                v
                for v in ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]
                if v not in placements
            ],
            "depth": d.depth(),
            "method": "Global position assignment maximizes platoon skill preference plus speed and position defense. Position rating ≥4; explicit locks first. Five starters, up to eight relievers and four bench bats. This optimizes the stated heuristic, not simulated runs or legal roster moves.",
        }

        if internal:
            from roster_moves import roster_moves

            result["moves"] = roster_moves(self, result)
            if result["moves"]["moves"]:
                result["warnings"].append(
                    "Internal selections are conditional: review each paired call-up/assignment, development readiness and roster eligibility before making moves."
                )
                result["ready_for_review"] = False
        return result

    def benchmarks(self, year=None):
        d = self.d
        year = int(year or d.year)
        from analytics import fip_constant

        selected_constant = fip_constant(
            d.baselines["pit"].get(year if year < d.year else d.base_year, {})
        )
        if not d.baselines["bat"].get(year, {}).get("pa"):
            year = d.base_year
        batting_rows = []
        pitching_rows = []
        for kind, rows, out in [
            ("bat", d.hist["bat"], batting_rows),
            ("pit", d.hist["pit"], pitching_rows),
        ]:
            for pid, rs in rows.items():
                r = next((x for x in rs if x["year"] == year), None)
                if not r:
                    continue
                p = d.by_id.get(pid)
                name = p["name"] if p else f"Player {pid}"
                out.append(
                    {
                        "id": pid,
                        "name": name,
                        "report_available": p is not None,
                        **(batting(r) if kind == "bat" else pitching(r, selected_constant)),
                    }
                )
        # Exposure thresholds scale with completed team games in a current season; prior seasons use full-season thresholds.
        with connect(d.sid) as con:
            gs = records(
                con,
                "select max(n) n from (select home_team,count(*) n from games where league_id=? and game_type=0 and year(date)=? and played=1 group by home_team)",
                [d.league, year],
            )
        games = number(gs[0]["n"]) if gs else 0
        pa = round(3.1 * games) if year == d.year and games else 502
        outs = round(3 * games) if year == d.year and games else 486
        qualified = [p for p in batting_rows if p["pa"] >= pa]
        qp = [p for p in pitching_rows if p["outs"] >= outs]
        relievers = [p for p in pitching_rows if p["outs"] >= 90 and p["gs"] < p["g"] * 0.5]
        with connect(d.sid) as con:
            team_records = records(con, "select * from team_record")
        standings = [
            {
                **t,
                "name": d.team_name(t["team_id"]),
                "division": d.teams[t["team_id"]].get("division_id"),
                "subleague": d.teams[t["team_id"]].get("sub_league_id"),
            }
            for t in team_records
            if d.teams.get(t["team_id"], {}).get("league_id") == d.league
        ]
        distributions = []
        for role, cohort in self.cohorts.items():
            if not cohort:
                continue
            kind = cohort[0]["kind"]
            table = "players_batting" if kind == "bat" else "players_pitching"
            prefix = "batting_ratings_overall_" if kind == "bat" else "pitching_ratings_overall_"
            for label, key in self.skill_specs(kind):
                vals = [number(d.ratings[table].get(p["id"], {}).get(prefix + key)) for p in cohort]
                distributions.append(
                    {
                        "role": role,
                        "label": label,
                        "key": key,
                        "mean": round(sum(vals) / len(vals), 2),
                        "n": len(vals),
                        "scale": [
                            {"rating": i, **percentile(vals, i), "count": vals.count(i)}
                            for i in range(1, 11)
                        ],
                    }
                )
        bands = {}
        for key, rs in [
            ("ops", qualified),
            ("obp", qualified),
            ("iso", qualified),
            ("era", qp),
            ("fip", qp),
            ("k_bb_pct", qp),
        ]:
            vals = sorted(p[key] for p in rs if p.get(key) is not None)
            if vals:
                bands[key] = {
                    "n": len(vals),
                    "cutoffs": {
                        str(q): vals[min(len(vals) - 1, int((len(vals) - 1) * q / 100))]
                        for q in [10, 25, 50, 75, 90, 95]
                    },
                    "lower_better": key in ["era", "fip"],
                }
        return {
            "year": year,
            "years": sorted(d.baselines["bat"], reverse=True),
            "current_year": d.year,
            "standings": standings,
            "baseline_bat": batting(d.baselines["bat"].get(year, {})),
            "baseline_pit": pitching(d.baselines["pit"].get(year, {}), selected_constant),
            "batting": qualified,
            "pitching": qp,
            "relievers": relievers,
            "pa_min": pa,
            "outs_min": outs,
            "distributions": distributions,
            "bands": bands,
            "checkpoints": self.state["checkpoints"],
            "note": "Leaderboards use exported season totals. Ratings describe currently assigned MLB players, grouped by inferred role, not every historical player. No games this season means last completed season leaders.",
        }

    def report(self, pid, intended_position=None):
        d = self.d
        p = d.by_id[int(pid)]
        r = d.player(int(pid))
        r["player"] = self.card(p)
        r["skills"] = self.skills(p)
        r["schedule"] = self.parks
        r["promotion"] = self.promotion(p)
        r["contract_schedule"] = self.contract_schedule(p)
        history = []
        available = [
            m
            for m in snapshots(d.manifest.get("source_id"))
            if m["created_at"] <= d.manifest["created_at"]
        ]
        checkpoint_ids = {x["snapshot"] for x in self.state["checkpoints"]}
        recent_ids = {m["id"] for m in available[:12]}
        for m in [m for m in available if m["id"] in recent_ids or m["id"] in checkpoint_ids]:
            with connect(m["id"]) as con:
                table = "players_batting" if p["kind"] == "bat" else "players_pitching"
                prefix = (
                    "batting_ratings_overall_"
                    if p["kind"] == "bat"
                    else "pitching_ratings_overall_"
                )
                cols = ",".join(prefix + k for _, k in self.skill_specs(p["kind"]))
                rows = records(con, f"select {cols} from {table} where player_id=?", [pid])
                if rows:
                    history.append(
                        {
                            "snapshot": m["id"],
                            "game_date": m["game_date"],
                            "ratings": {
                                label: rows[0][prefix + k]
                                for label, k in self.skill_specs(p["kind"])
                            },
                        }
                    )
        r["rating_history"] = history
        r["decisions"] = [
            x
            for x in self.state["decisions"]
            if pid
            in [
                x["case"].get("player_id"),
                *x["case"].get("send", []),
                *x["case"].get("receive", []),
            ]
        ]
        r["notes"] = [
            x
            for x in read_json(DATA / "journal.json", [])
            if x.get("player_id") == pid and x.get("source") in (None, d.manifest.get("source_id"))
        ]
        from scouting import ScoutingReport

        report = ScoutingReport(self)
        position = (
            intended_position or ("SP" if self.role(p) == "Starters" else "RP")
            if p["kind"] == "pit"
            else intended_position or p["position"]
        )
        r["assessment"] = report.assessment(p, position)
        if p["kind"] == "pit" and p in d.own():
            plan = self.roster()["pitching_recommendations"]
            r["pitching_usage"] = next(
                (x for x in plan["rotation"] + plan["bullpen"] if x["id"] == p["id"]), None
            )
        return r

    def contract_schedule(self, p):
        d = self.d
        result = []
        for source, c in [
            ("Current contract", d.contracts.get(p["id"], {})),
            ("Signed extension", d.extensions.get(p["id"], {})),
        ]:
            start = int(number(c.get("season_year")))
            years = int(number(c.get("years")))
            for i in range(min(years, 15)):
                if start + i < d.year:
                    continue
                optprefix = (
                    "last_year_" if i == years - 1 else "next_last_year_" if i == years - 2 else ""
                )
                types = [
                    name
                    for name, key in [
                        ("Team", "team_option"),
                        ("Player", "player_option"),
                        ("Vesting", "vesting_option"),
                    ]
                    if optprefix and c.get(optprefix + key)
                ]
                result.append(
                    {
                        "year": start + i,
                        "salary": number(c.get(f"salary{i}")),
                        "type": " / ".join(types) + " option" if types else "Scheduled",
                        "buyout": number(c.get(optprefix + "option_buyout")) if optprefix else 0,
                        "source": source,
                    }
                )
        return sorted(result, key=lambda x: (x["year"], x["source"]))

    def promotion(self, p):
        d = self.d
        rt = d.roster.get(p["id"], {})
        rules = d.leagues[d.league]
        used = sum(x["secondary"] for x in d.own())
        active = len(d.active())
        notes = []
        if p["injured"] or p["on_dl"]:
            notes.append("Injury flag: check availability and injured-list rules first.")
        if not p["secondary"]:
            notes.append(
                f"Needs a 40-man place: {used}/{int(number(rules.get('rules_secondary_roster_limit'),40))} exported across the organization; injured-list exceptions need confirmation."
            )
        notes.append(
            f"Active roster: {active}/{int(number(rules.get('rules_active_roster_limit'),26))} healthy active. Count and legality must be checked in OOTP."
        )
        notes.append(
            "A top prospect needs regular playing time and a development plan. Current talent and projected rate alone do not prove readiness."
        )
        notes.append(
            "172 service days make a full year. Delaying a debut can affect control, but Super Two thresholds vary; no universal safe promotion date is assumed."
        )
        return {
            "service_days": rt.get("mlb_service_days"),
            "service_years": rt.get("mlb_service_years"),
            "days_this_year": rt.get("mlb_service_days_this_year"),
            "options_used": rt.get("options_used"),
            "options_used_this_year": rt.get("options_used_this_year"),
            "secondary": p["secondary"],
            "notes": notes,
            "arb_min": rules.get("rules_salary_arbitration_minimum_years"),
            "fa_min": rules.get("rules_fa_minimum_years"),
        }

    def finances(self):
        d = self.d
        f = d.finances()
        years = []
        for yr in range(d.year, d.year + 7):
            total = conditional = 0
            extension = 0
            for p in d.own():
                rows = [r for r in self.contract_schedule(p) if r["year"] == yr]
                # A signed extension takes precedence if export rows overlap; expose it instead of adding both.
                ext = [r for r in rows if r["source"] == "Signed extension"]
                row = ext or rows
                if row:
                    r = row[-1]
                    total += r["salary"]
                    conditional += r["salary"] if "option" in r["type"] else 0
                    extension += r["salary"] if ext else 0
            years.append(
                {
                    "year": yr,
                    "scheduled": total,
                    "conditional": conditional,
                    "non_option": total - conditional,
                    "extension": extension,
                    "mode": self.b["seasons"].get(str(yr), "Unplanned"),
                }
            )
        expiring = [
            self.card(p)
            for p in d.own()
            if p["salary_known"] and not any(r["year"] > d.year for r in self.contract_schedule(p))
        ]
        return {
            **f,
            "schedule": years,
            "reported_funds": f["financials"].get("cash_trades_available"),
            "budget_less_payroll": f["financials"]["budget"] - f["financials"]["player_payroll"],
            "expiring": expiring,
            "note": "Cash trades available is the exported field, pending exact UI reconciliation. Budget less payroll is context, not spendable cash. Option salaries are conditional; bonuses, renewals and arbitration remain outside the schedule.",
        }

    def acquisitions(self, free=False, position=""):
        d = self.d
        ps = [
            p
            for p in d.profiles
            if p["organization_id"] != d.team
            and p["team_id"] != d.team
            and not p["draft_eligible"]
            and (p["free_agent"] or p["league_id"] == d.league)
            and (not free or p["free_agent"])
            and (not position or p["position"] == position)
        ]
        ranked = sorted([self.card(p) for p in ps], key=lambda x: x["grade"], reverse=True)
        own = sorted(
            [
                self.card(p)
                for p in d.own()
                if not p["injured"] and (not position or p["position"] == position)
            ],
            key=lambda x: x["grade"],
            reverse=True,
        )
        from acquisition import market_context

        roster = self.roster()
        incumbents = {x["position"]: x["player"] for x in roster["lineup"]}
        for role, rs in [("SP", roster["rotation"]), ("RP", roster["bullpen"])]:
            people = [x["player"] for x in rs if x["player"]]
            incumbents[role] = min(people, key=lambda p: p["grade"]) if people else None
        from owner_goals import owner_context

        owner = owner_context(self)
        owner_positions = {
            g["position"]
            for g in owner["goals"]
            if g["category"] == "Position upgrade" and g["position"]
        }
        weak = {
            k
            for k, v in sorted(incumbents.items(), key=lambda x: x[1]["grade"] if x[1] else -1)[:4]
        }
        weak.add("SP")
        weak.update(owner_positions)
        for p in ranked:
            table = "players_batting" if p["kind"] == "bat" else "players_pitching"
            raw = d.by_id[p["id"]]
            m = market_context(
                p,
                d.ratings["players_value"].get(p["id"], {}),
                d.ratings[table].get(p["id"], {}),
                d.ratings["players_fielding"].get(p["id"], {}),
                number(d.leagues[d.league].get("rules_fa_minimum_years"), 6),
            )
            role = (
                ("SP" if self.role(raw) == "Starters" else "RP")
                if p["kind"] == "pit"
                else p["position"]
            )
            inc = incumbents.get(role)
            delta = round(p["grade"] - inc["grade"], 1) if inc else None
            m.update(
                role=role,
                incumbent=inc["name"] if inc else None,
                incumbent_id=inc["id"] if inc else None,
                grade_difference=delta,
                need=bool(position or role in weak),
                upgrade=bool(inc is None or delta >= 0.3),
                locked=bool(
                    inc
                    and any(
                        l["scope"] in ["roster", "lineup", "rotation", "bullpen"]
                        for l in inc["locks"]
                    )
                ),
                salary_difference=(
                    round(p["salary"] - inc["salary"])
                    if inc and p["salary_known"] and inc["salary_known"]
                    else None
                ),
            )
            p["acquisition"] = m
        premium = [p for p in ranked if p["acquisition"]["premium"]]
        practical = [
            p
            for p in ranked
            if not p["acquisition"]["premium"]
            and p["acquisition"]["need"]
            and p["acquisition"]["upgrade"]
            and not p["injured"]
            and not p["on_dl"]
        ]
        practical.sort(
            key=lambda p: (
                p["free_agent"],
                p["acquisition"]["role"] in owner_positions,
                p["grade"],
            ),
            reverse=True,
        )
        protected = {l["player_id"] for l in self.state["locks"] if l["scope"] == "trade"}
        selling = [
            self.card(p)
            for p in d.own()
            if p["salary_known"]
            and p["id"] not in protected
            and (
                not any(r["year"] > d.year for r in self.contract_schedule(p))
                or (self.b["seasons"].get(str(d.year + 1)) == "Rebuild")
            )
        ]
        selling.sort(key=lambda x: (x["years_left"], -x["grade"]))
        edges = []
        for p in ranked:
            if (
                p["acquisition"]["premium"]
                or not p["acquisition"]["need"]
                or not p["acquisition"]["upgrade"]
                or not p["salary_known"]
                or not 0 < p["salary"] <= 8000000
                or p["injured"]
                or p["on_dl"]
            ):
                continue
            r = d.ratings["players_batting" if p["kind"] == "bat" else "players_pitching"].get(
                p["id"], {}
            )
            observed = p["recorded"] or {}
            signals = []
            if p["kind"] == "bat":
                gap = number(r.get("batting_ratings_overall_gap"))
                eye = number(r.get("batting_ratings_overall_eye"))
                speed = number(r.get("running_ratings_speed"))
                if gap >= 8:
                    signals.append(
                        f"Gap power {gap:g}/10; home doubles/triples fit, a skill OPS alone can obscure."
                    )
                if eye >= 8:
                    signals.append(
                        f"Plate discipline {eye:g}/10; inspect affordable on-base production."
                    )
                if number(observed.get("pa")) >= 200 and number(observed.get("bb_pct")) >= 0.12:
                    signals.append(
                        f"Recorded {p['recorded_year']} walk rate {100*observed['bb_pct']:.1f}% over {observed['pa']:g} PA."
                    )
                defense = d.ratings["players_fielding"].get(p["id"], {})
                positions = [
                    POSITIONS[c]
                    for c in range(2, 10)
                    if number(defense.get(f"fielding_rating_pos{c}")) >= 6
                ]
                if len(positions) >= 2:
                    signals.append(
                        "Defensive versatility: " + ", ".join(positions) + ", position ratings ≥6."
                    )
                if speed >= 8:
                    signals.append(
                        f"Speed {speed:g}/10; review baserunning success and a role before assigning run value."
                    )
            else:
                if number(observed.get("outs")) >= 90 and number(observed.get("k_bb_pct")) >= 0.18:
                    signals.append(
                        f"Recorded {p['recorded_year']} K−BB% {100*observed['k_bb_pct']:.1f}% over {observed['ip_display']} IP."
                    )
                if number(r.get("pitching_ratings_overall_control")) >= 7:
                    signals.append("Control ≥7/10; check strikeout and HR prevention alongside it.")
            if signals:
                edges.append(
                    {
                        "player": p,
                        "signals": signals,
                        "status": "Research signal — price edge unproven",
                    }
                )
        edges.sort(
            key=lambda x: (len(x["signals"]), x["player"]["grade"], -x["player"]["salary"]),
            reverse=True,
        )
        return {
            "owner_goals": owner,
            "players": practical,
            "all_players": ranked,
            "premium": premium,
            "internal": [
                {**incumbents[k], "comparison_role": k}
                for k in (
                    ["SP", "RP"] if position == "P" else [position] if position else sorted(weak)
                )
                if incumbents.get(k)
            ],
            "selling": selling,
            "edges": edges[:20],
            "trade_block": "Unverified: trade_status exists in the CSV, but its code-to-availability mapping has not been confirmed. Other-club players below are research targets, not declared available.",
            "edge": "Edgehunter hypotheses: strong OBP ratings, useful platoon skills or park-fit gap power. Confirm asking price, development cost and replacement value before calling any player a bargain.",
        }

    def development(self):
        d = self.d
        dev = d.development()
        prospects = dev["prospects"]
        draft = [p for p in d.profiles if p["draft_eligible"]]
        depth = collections.Counter(p["position"] for p in d.own() if p["team_id"] != d.team)

        def talent(p):
            return number(d.ratings["players_value"].get(p["id"], {}).get("pot_rating"))

        # Needs break ties within a displayed talent tier; never outrank a higher tier.
        draft.sort(
            key=lambda p: (talent(p), -depth[p["position"]], p["engine_potential"]), reverse=True
        )
        return {
            **dev,
            "prospects": [self.card(p) for p in prospects[:75]],
            "draft": [
                {**self.card(p), "talent_tier": talent(p), "depth_count": depth[p["position"]]}
                for p in draft[:75]
            ],
            "depth": dict(depth),
            "note": "Draft candidates are export-flagged eligible, not verified as available for your next pick. Potential tier comes first; organizational scarcity breaks ties within a tier. Potential is not a development guarantee.",
        }

    def changes(self):
        d = self.d
        prev = [
            m
            for m in snapshots(d.manifest.get("source_id"))
            if m["created_at"] < d.manifest["created_at"]
        ]
        if not prev:
            return {
                "previous": None,
                "items": [],
                "note": "Your first snapshot establishes the baseline. Export again after game changes to see differences.",
            }
        from department import department

        old = department(prev[0]["id"])
        items = []
        for p in d.own():
            q = old.by_id.get(p["id"])
            if not q:
                items.append({"id": p["id"], "name": p["name"], "change": "Added to organization"})
                continue
            changed = [
                f'{k.replace("_"," ")}: {q.get(k)} → {p.get(k)}'
                for k in ["team", "injured", "active", "salary", "engine_value", "engine_potential"]
                if p.get(k) != q.get(k)
            ]
            if changed:
                items.append({"id": p["id"], "name": p["name"], "change": "; ".join(changed)})
        for q in old.own():
            if q["id"] not in {p["id"] for p in d.own()}:
                items.append({"id": q["id"], "name": q["name"], "change": "Left organization"})
        return {
            "previous": prev[0]["id"],
            "items": items,
            "note": "Compared with the preceding captured export; multiple captures on the same game date may have identical data.",
        }

    def home(self):
        from season_projection import season_projection

        d = self.d
        r = self.roster()
        b = d.briefing()
        try:
            prediction = season_projection(d)
        except ValueError as error:
            prediction = {"error": str(error)}
        lineup = [x["player"] for x in r["lineup"]]
        starters = [x["player"] for x in r["rotation"] if x["player"]]
        groups = [
            ("Offense", lineup),
            ("Rotation", starters),
            ("Bullpen", [x["player"] for x in r["bullpen"]]),
        ]
        outlook = [
            {
                "name": name,
                "grade": round(sum(x["grade"] for x in ps) / len(ps), 1) if ps else None,
                "count": len(ps),
            }
            for name, ps in groups
        ]
        return {
            "prediction": prediction,
            "briefing": b,
            "roster": r,
            "outlook": outlook,
            "blueprint": self.b,
            "changes": self.changes(),
            "watchlist": self.state["watchlist"],
            "locks": self.state["locks"],
            "summary": f"{d.team_name(d.team)} are in {self.b['seasons'].get(str(d.year),'unplanned').lower()} mode. {r['shape']}; review the back end and injury coverage before advancing.",
            "schedule": self.parks,
            "decisions": self.state["decisions"][:5],
        }


def evaluate(d, case):
    o = Office(d)
    kind = case.get("type", "Replacement")
    pid = int(case.get("player_id") or 0)
    p = d.by_id.get(pid)
    override = bool(case.get("override"))
    protected = {l["player_id"] for l in o.state["locks"] if l["scope"] == "trade"}
    if kind == "Offers":
        from offers import compare_offers

        send = [int(i) for i in case.get("send", [])]
        if protected.intersection(send) and not override:
            raise ValueError(
                "A player on the block is trade-protected. Keep the lock or compare an unlocked "
                "scenario; standing locks remain unchanged."
            )
        mode = case.get("scenario_mode") or o.b["seasons"].get(str(d.year))
        if mode not in MODES:
            raise ValueError("Unknown scenario direction.")
        report = compare_offers(o, send, case.get("offers", []), mode)
        block = ", ".join(d.by_id[i]["name"] for i in send)
        report.update(
            question=case.get("question") or f"Which offer for {block} should we take?",
            game_date=d.manifest["game_date"],
            snapshot=d.sid,
            locks_respected=not override,
            alternatives=[],
            checks=["Make the trade in OOTP; saving this comparison does not move players."],
        )
        return report
    if kind not in ["Replacement", "Promotion", "Signing", "Trade", "Extension", "Deadline plan"]:
        raise ValueError("Choose a supported decision type.")
    pos = case.get("position") or (p["position"] if p else "P")
    assumptions = {
        "annual_offer": number(case.get("annual_offer")),
        "offer_years": int(number(case.get("offer_years"), 1)),
        "added_service_days": int(number(case.get("added_service_days"))),
        "scenario_mode": case.get("scenario_mode") or o.b["seasons"].get(str(d.year)),
    }
    if (
        not 1 <= assumptions["offer_years"] <= 15
        or not 0 <= assumptions["annual_offer"] <= 100000000
        or not 0 <= assumptions["added_service_days"] <= 172
    ):
        raise ValueError("Use valid offer years, salary and service-day assumptions.")
    mode = assumptions["scenario_mode"]
    if mode not in MODES:
        raise ValueError("Unknown scenario direction.")
    from owner_goals import owner_context

    base = {
        "owner_goals": owner_context(o),
        "type": kind,
        "question": case.get("question") or f'{kind}: {p["name"] if p else pos}',
        "blueprint": o.b,
        "scenario_mode": mode,
        "assumptions": assumptions,
        "snapshot": d.sid,
        "game_date": d.manifest["game_date"],
        "alternatives": [],
        "checks": [
            "Verify current roster, options and injury status in OOTP.",
            "Confirm the financial screen and asking price before agreeing.",
        ],
        "locks_respected": not override,
        "recommendation": "No clear winner until cost and availability are confirmed.",
    }
    base["alternatives"].append(
        {
            "name": "Do nothing",
            "summary": "Keep current assignments and commitments. Avoid acquisition cost, but leave the identified need unresolved.",
        }
    )
    if kind == "Trade":
        send = [int(i) for i in case.get("send", [])]
        recv = [int(i) for i in case.get("receive", [])]
        blocked = protected.intersection(send)
        if blocked and not override:
            raise ValueError(
                "A proposed outgoing player is trade-protected. Keep the lock or explicitly evaluate an unlocked scenario; standing locks remain unchanged."
            )
        package = d.scenario(send, recv)
        base["package"] = package
        from trade_review import analyze_trade
        from trade_call import trade_call

        base["trade_review"] = analyze_trade(o, send, recv, mode)
        base["call"] = trade_call(o, send, recv, mode, base["trade_review"])
        call = base["call"]
        base["recommendation"] = (
            call["call"] + (" " if call["call"].endswith("...") else ". ") + call["headline"]
        )
        outgoing = [o.card(d.by_id[i]) for i in send]
        incoming = [o.card(d.by_id[i]) for i in recv]
        base["outgoing"] = outgoing
        base["incoming"] = incoming
        base["alternatives"].append(
            {
                "name": "Proposed package",
                "summary": f"{len(outgoing)} outgoing / {len(incoming)} incoming. Current-year scheduled payroll changes by ${package['years'][0]['payroll_change']:,.0f}. Grades describe rate preferences, not additive trade value.",
            }
        )
        if blocked:
            base["checks"].append(
                "Unlocked scenario only: standing trade protection is still saved and binding."
            )
        if mode in ["Selective sell", "Rebuild"] and o.b["seasons"].get(str(d.year + 1)) in [
            "Win now",
            "All in",
        ]:
            base["checks"].append(
                "Preserve next season’s contender: favor selling expiring pieces before long-term core contracts."
            )
    elif kind == "Extension":
        if not p:
            raise ValueError("Select a player to review.")
        base["player"] = o.report(pid)
        base["offer_total"] = assumptions["annual_offer"] * assumptions["offer_years"]
        base["start_year"] = int(number(case.get("start_year"), d.year + 1))
        base["overlap"] = [
            r
            for r in o.contract_schedule(p)
            if base["start_year"] <= r["year"] < base["start_year"] + assumptions["offer_years"]
        ]
        base["alternatives"].append(
            {
                "name": "Proposed extension",
                "summary": f"${base['offer_total']:,.0f} over {assumptions['offer_years']} years, beginning {base['start_year']}. Offer is a manual assumption, not the player’s asking price.",
            }
        )
        if base["overlap"]:
            base["checks"].append(
                "Offer overlaps scheduled contract years. Treat as renegotiation/replace covered years; do not add both salaries."
            )
        base["checks"].append(
            "Check options, opt-outs, age risk and market alternatives; no acceptance prediction."
        )
    elif kind == "Deadline plan":
        a = o.acquisitions()
        base["candidates"] = a["selling"][:15]
        base["alternatives"].append(
            {
                "name": "Selective sale",
                "summary": "Review expiring contracts first. Keep long-term contributors when next season remains win now.",
            }
        )
        base["recommendation"] = (
            "Use selective selling rather than an automatic teardown if next year is still a contender."
            if o.b["seasons"].get(str(d.year + 1)) == "Win now"
            else "Match sales to the next two seasons, protecting the value of controllable talent."
        )
    else:
        code = next((k for k, v in POSITIONS.items() if v == pos), None)
        pool = [
            x
            for x in d.own()
            if x["id"] != pid
            and not x["injured"]
            and not x["on_dl"]
            and not x["dfa"]
            and not x["on_waivers"]
            and (
                x["kind"] == "pit" and o.role(x) == "Starters"
                if pos == "P"
                else x["kind"] == "bat"
                and (
                    pos == "DH"
                    or number(
                        d.ratings["players_fielding"]
                        .get(x["id"], {})
                        .get(f"fielding_rating_pos{code}")
                    )
                    >= 4
                )
            )
        ]
        if kind == "Replacement" and pos == "P":
            assigned = {x["player"]["id"] for x in o.roster()["rotation"] if x["player"]}
            pool = [x for x in pool if x["id"] not in assigned]
        if kind == "Promotion" and p and not p["injured"] and not p["on_dl"]:
            pool = [p] + pool
        internal = sorted([o.card(x) for x in pool], key=lambda x: x["grade"], reverse=True)[:5]
        external = o.acquisitions(True, pos)["players"][:5]
        base["internal"] = internal
        base["external"] = external
        for x in internal[:3]:
            base["alternatives"].append(
                {
                    "name": x["name"],
                    "player_id": x["id"],
                    "summary": x["summary"]
                    + " "
                    + (
                        "Already active; avoids an outside acquisition."
                        if x["active"]
                        else "Internal option: confirm readiness, roster room and playing time."
                    ),
                }
            )
        if internal:
            best = internal[0]
            base["recommendation"] = (
                f"Review {best['name']} first as the strongest available internal preference fit; compare development and roster costs before making the move."
            )
            base["promotion"] = o.promotion(d.by_id[best["id"]])
            days = number(base["promotion"]["service_days"])
            base["service_scenario"] = {
                "current_days": days,
                "assumed_added_days": assumptions["added_service_days"],
                "projected_total": days + assumptions["added_service_days"],
                "full_years": int((days + assumptions["added_service_days"]) // 172),
                "note": "Illustrative cumulative service only; game service credits, arbitration and Super Two eligibility must be verified.",
            }
        if kind == "Signing" and p:
            base["player"] = o.card(p)
            base["alternatives"].append(
                {
                    "name": "Sign selected player",
                    "player_id": pid,
                    "summary": p["name"]
                    + " requires a confirmed asking price, role and roster place.",
                }
            )
            base["offer_total"] = assumptions["annual_offer"] * assumptions["offer_years"]
    base["why"] = (
        "Preferences combine current ratings, conservative completed-season MLB forecasts and schedule-weighted park fit. They guide a review; they do not certify a move’s legality or predict trade acceptance."
    )
    if kind == "Trade":
        base["why"] = base["recommendation"]
    base["financial_context"] = {
        "reported_cash_trades_available": d.financials[d.team].get("cash_trades_available"),
        "current_payroll": d.financials[d.team].get("player_payroll"),
        "manual_offer_total": assumptions["annual_offer"] * assumptions["offer_years"],
        "note": "Exported funds require game-screen reconciliation. Manual offers do not imply player acceptance.",
    }
    if kind in ["Signing", "Extension"]:
        if not assumptions["annual_offer"]:
            base["checks"].append(
                "No offer amount supplied: financial comparison is incomplete; a zero is not a free acquisition."
            )
        base["offer_schedule"] = [
            {
                "year": (
                    int(number(case.get("start_year"), d.year + 1)) + i
                    if kind == "Extension"
                    else d.year + i
                ),
                "annual_offer": assumptions["annual_offer"],
            }
            for i in range(assumptions["offer_years"])
        ]
    if "Promotion" == kind and p and (p["injured"] or p["on_dl"]):
        base["checks"].append("Selected prospect is injured; do not treat him as ready to play.")
    if kind in ("Signing", "Extension", "Promotion") and p:
        from player_calls import extension_call, promotion_call, signing_call

        years = int(number(case.get("offer_years")))  # 0 = let the assistant GM pick the length
        if kind == "Signing":
            c = signing_call(o, p, assumptions["annual_offer"], years, mode)
        elif kind == "Extension":
            start = int(number(case.get("start_year"))) or None
            c = extension_call(o, p, assumptions["annual_offer"], years, start, mode)
        else:
            c = promotion_call(o, p, mode)
        base["call"] = c
        base["recommendation"] = (
            c["call"] + (" " if c["call"].endswith("...") else ". ") + c["headline"]
        )
        base["why"] = base["recommendation"]
    return base
