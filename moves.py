"""The assistant GM's suggested moves: who should come up, who should play, who goes down, and
everything that moves with it.

Baseball isn't apples to apples: a call-up bumps someone from the rotation to the bullpen, which
bumps the last arm out of the pen, which needs an option or a 40-man spot. Each suggestion is a
chain of those steps plus a side-by-side comparison with real stat lines and league context
("3.07 FIP, 26% K, top 3% of the IL"), tools, and what each player projects to be worth to us.

Four kinds of suggestion:
- Do it:        a clear upgrade by projection, or a hole that needs filling
- Worth a look: a minor leaguer dominating his league while our starter there is struggling
                (a bet on results over ratings, said out loud)
- Be ready:     a day-to-day starter; if he lands on the IL, here's the chain
- Depth:        who's next in line, and where
"""

from analytics import BAT_FIELDS, PIT_FIELDS, batting, combine, fip_constant, number, pitching
from frontoffice import percentile
from storage import connect, records
from roster_moves import option_review
from value import value_engine

LEVELS = {1: "MLB", 2: "AAA", 3: "AA", 4: "A-ball", 6: "Rookie ball"}
POSITION_CODES = {"C": 2, "1B": 3, "2B": 4, "3B": 5, "SS": 6, "LF": 7, "CF": 8, "RF": 9}
UPGRADE = {"sp": 0.5, "rp": 0.3, "bat": 0.6}  # wins a season a newcomer must add to be worth it
HOT = 85  # a minor leaguer in the top 15% of his league is forcing the issue
STRUGGLING = 40  # a big leaguer in the bottom 40% of the league is fair game
MIN_SAMPLE = {"pit": 30, "bat": 100}  # outs / PA before a second-level line is worth showing
MAX_MOVES = 6


class Moves:
    def __init__(self, office):
        self.o, self.d = office, office.d
        self.e = value_engine(self.d)
        self.this_year = season_index(self.d)
        self.roster = office.roster("vsr", False)
        self.locked = {l["player_id"] for l in office.state["locks"]}
        self._stats = {}
        self.org = [
            p
            for p in self.d.own()
            if not p["free_agent"] and not p["injured"] and not p["on_dl"] and not p["dfa"]
        ]
        self.active = [p for p in self.org if p["team_id"] == self.d.team and p["active"]]
        self.used = set()  # players already in a suggestion, so nobody is promised twice

    # ---- facts about one player -----------------------------------------------------------

    def rate(self, p, role=None):
        """Full-season wins in a role. His own role blends real results; another role uses ratings."""
        role = role or self.e.role(p)
        if role == self.e.role(p):
            return self.e.current_rate(p)
        return self.e.war_rate(role, self.e.rating(p)[0])

    def seasons(self, p):
        """(line where he is now, a meaningful line at another level this year)."""
        if p["id"] not in self._stats:
            mine = self.this_year.get((p["kind"], p["id"]), [])
            now = self.e.level(p) or 1
            here = next((r for r in mine if r["level"] == now), None)
            key = "outs" if p["kind"] == "pit" else "pa"
            other = [
                r for r in mine if r is not here and number(r.get(key)) >= MIN_SAMPLE[p["kind"]]
            ]
            elsewhere = max(other, key=lambda r: number(r.get(key)), default=None)
            self._stats[p["id"]] = (here or elsewhere, elsewhere if here else None)
        return self._stats[p["id"]]

    def percentile(self, p):
        s = self.seasons(p)[0]
        return s["quality_percentile"] if s and s["qualified"] else None

    def hot(self, p):
        s = self.seasons(p)[0]
        return bool(s and s["level"] > 1 and (self.percentile(p) or 0) >= HOT)

    def struggling(self, p):
        s = self.seasons(p)[0]
        pct = self.percentile(p)
        return bool(s and s["level"] == 1 and pct is not None and pct < STRUGGLING)

    def where(self, p):
        level = self.e.level(p) or 1
        if level == 1:
            if p["team_id"] == self.d.team:
                return str(self.d.teams.get(self.d.team, {}).get("name") or "Our club")
            return self.d.team_name(p["team_id"])
        return f"{LEVELS.get(level, 'minors')} {self.d.team_name(p['team_id'])}".strip()

    def can_play(self, p, pos):
        if pos == "DH" or p["position"] == pos:
            return True
        code = POSITION_CODES.get(pos)
        rating = (
            self.d.ratings["players_fielding"].get(p["id"], {}).get(f"fielding_rating_pos{code}")
        )
        return number(rating) >= 5

    def tools(self, p):
        if p["kind"] == "pit":
            r = self.d.ratings["players_pitching"].get(p["id"], {})
            parts = [
                ("stuff", r.get("pitching_ratings_overall_stuff")),
                ("movement", r.get("pitching_ratings_overall_movement")),
                ("control", r.get("pitching_ratings_overall_control")),
                ("stamina", r.get("pitching_ratings_misc_stamina")),
            ]
        else:
            r = self.d.ratings["players_batting"].get(p["id"], {})
            parts = [
                ("contact", r.get("batting_ratings_overall_contact")),
                ("power", r.get("batting_ratings_overall_power")),
                ("eye", r.get("batting_ratings_overall_eye")),
                ("avoid K", r.get("batting_ratings_overall_strikeouts")),
            ]
        return ", ".join(f"{name} {int(number(v))}" for name, v in parts if number(v) > 0)

    def line(self, p):
        here, elsewhere = self.seasons(p)
        if not here:
            return "no stats this year"
        text = stat_text(p, here)
        key, floor = ("outs", 30) if p["kind"] == "pit" else ("pa", 50)
        if number(here.get(key)) < floor:
            text += " (small sample)"
        if elsewhere:
            text += f". Also {LEVELS.get(elsewhere['level'], elsewhere['league'])}: {stat_text(p, elsewhere, short=True)}"
        if p.get("day_to_day"):
            text += ". Day-to-day"
        return text

    def card(self, p, role, label):
        return {
            "id": p["id"],
            "name": p["name"],
            "role": label,
            "where": self.where(p),
            "age": p["age"],
            "line": self.line(p),
            "tools": self.tools(p),
            "wins": round(self.rate(p, role), 1),
            "options": (
                option_review(self.d.roster.get(p["id"], {}))[0]
                if p["team_id"] == self.d.team
                else None
            ),
        }

    # ---- roster bookkeeping ------------------------------------------------------------------

    def on_forty(self, p):
        return bool(p.get("secondary")) or (p["team_id"] == self.d.team and p["active"])

    def forty_man_step(self, p):
        if self.on_forty(p):
            return None
        forty = [q for q in self.d.own() if self.on_forty(q)]
        limit = int(number(self.d.leagues[self.d.league].get("rules_secondary_roster_limit"), 40))
        if len(forty) < limit:
            return f"Add {p['name']} to the 40-man roster ({len(forty)} of {limit} spots used)."
        spare = min(
            (q for q in forty if not (q["team_id"] == self.d.team and q["active"])),
            key=self.rate,
            default=None,
        )
        if spare:
            return (
                f"The 40-man is full: designate {spare['name']} ({self.where(spare)}) for "
                f"assignment to make room for {p['name']}."
            )
        return f"The 40-man is full: open a spot for {p['name']} (DFA or 60-day IL)."

    def send_down(self, p):
        label, detail = option_review(self.d.roster.get(p["id"], {}))
        if label == "Conditional option to AAA":
            return f"Option {p['name']} to AAA."
        return f"Send {p['name']} out ({label.lower()}: {detail})"

    def active_room(self):
        limit = int(number(self.d.leagues[self.d.league].get("rules_active_roster_limit"), 26))
        return limit - len(self.active)

    def paperwork(self, newcomer):
        """The 40-man spot and service clock that come with a call-up."""
        steps = [self.forty_man_step(newcomer)]
        if newcomer["service_years"] == 0:
            steps.append(f"Starts {newcomer['name']}'s big-league service clock.")
        return [s for s in steps if s]

    def arrival_steps(self, newcomer, odd_man_pool):
        """Who leaves the active roster when someone comes up, plus the paperwork."""
        steps = []
        if self.active_room() > 0:
            steps.append(f"There's an open spot on the active roster ({self.active_room()} open).")
        else:
            out = min(
                (
                    q
                    for q in odd_man_pool
                    if q["id"] not in self.locked and q["id"] not in self.used
                ),
                key=self.rate,
                default=None,
            )
            if out:
                steps.append(f"{out['name']} is the odd man out: {self.send_down(out)}")
        return steps + self.paperwork(newcomer)

    # ---- the suggestions -------------------------------------------------------------------

    def rotation(self):
        moves = []
        slots = self.roster["rotation"]
        starters = [x["player"] for x in slots if x["player"]]
        bullpen = [x["player"] for x in self.roster["bullpen"] if x["player"]]
        in_mlb = {p["id"] for p in starters + bullpen}
        pool = sorted(
            (
                p
                for p in self.org
                if p["kind"] == "pit"
                and p["id"] not in in_mlb
                and p.get("role_code") == 11
                and (self.e.level(p) or 9) <= 3
            ),
            key=lambda p: (self.hot(p), self.rate(p, "sp")),
            reverse=True,
        )

        def next_arm():
            return next((c for c in pool if c["id"] not in self.used), None)

        for x in slots:
            if x["player"] or not next_arm():
                continue
            c = next_arm()
            self.used.add(c["id"])
            moves.append(
                self.move(
                    "Rotation",
                    "Do it",
                    f"Fill the #{x['slot']} spot with {c['name']}",
                    f"We only have {len(starters)} healthy starters, and {c['name']} is the best arm ready.",
                    self.rate(c, "sp"),
                    [f"Call up {c['name']} from {self.where(c)} for the #{x['slot']} spot."]
                    + self.arrival_steps(c, bullpen),
                    [self.card(c, "sp", "Call up")]
                    + [
                        self.card(o, "sp", "Other option") for o in pool if o["id"] not in self.used
                    ][:2],
                )
            )
        movable = [p for p in starters if p["id"] not in self.locked]
        weakest = min(movable, key=lambda p: self.rate(p, "sp"), default=None)
        worst_now = min(
            (p for p in movable if self.struggling(p)), key=self.percentile, default=None
        )
        c = next_arm()
        if c and weakest and self.rate(c, "sp") - self.rate(weakest, "sp") >= UPGRADE["sp"]:
            self.used.add(c["id"])
            moves.append(self.swap_starter(c, weakest, bullpen, "Do it"))
        elif (
            c
            and worst_now
            and self.hot(c)
            and self.rate(c, "sp") >= self.rate(worst_now, "sp") - 1.0
        ):
            self.used.add(c["id"])
            moves.append(self.swap_starter(c, worst_now, bullpen, "Worth a look"))
        for p in starters:  # day-to-day starters: have the chain ready
            c = next_arm()
            if p.get("day_to_day") and c:
                moves.append(
                    self.move(
                        "Rotation",
                        "Be ready",
                        f"If {p['name']} lands on the IL, {c['name']} takes his turn",
                        f"{p['name']} is day-to-day. {c['name']} is our first call"
                        + (" and he's dominating his league." if self.hot(c) else "."),
                        0,
                        [
                            f"Place {p['name']} on the IL.",
                            f"Call up {c['name']} from {self.where(c)} to start in his place.",
                        ]
                        + self.paperwork(c),
                        [self.card(c, "sp", "First call"), self.card(p, "sp", "Day-to-day")],
                    )
                )
                self.used.add(c["id"])
        return moves

    def swap_starter(self, c, out, bullpen, call):
        gain = self.rate(c, "sp") - self.rate(out, "sp")
        to_pen = self.rate(out, "rp") > min([self.rate(b) for b in bullpen] or [0])
        chain = [f"Call up {c['name']} from {self.where(c)} to take {out['name']}'s turn."]
        if to_pen:
            chain.append(f"{out['name']} moves to the bullpen as a long man.")
            chain += self.arrival_steps(c, bullpen)
        else:
            chain.append(self.send_down(out))
            chain += self.paperwork(c)
        if call == "Do it":
            why = f"{c['name']} projects better than {out['name']} right now."
        else:
            why = (
                f"{c['name']} is dominating his league while {out['name']} is struggling. His ratings "
                f"say {self.rate(c, 'sp'):.1f} wins a season against {self.rate(out, 'sp'):.1f}, so this "
                "is a bet on the results."
            )
        return self.move(
            "Rotation",
            call,
            f"{c['name']} for {out['name']}",
            why,
            max(gain, 0),
            chain,
            [self.card(c, "sp", "Call up"), self.card(out, "sp", "Our starter")],
        )

    def bullpen(self):
        pen = [x["player"] for x in self.roster["bullpen"] if x["player"]]
        rotation = {x["player"]["id"] for x in self.roster["rotation"] if x["player"]}
        taken = {p["id"] for p in pen} | rotation
        pool = sorted(
            (
                p
                for p in self.org
                if p["kind"] == "pit"
                and p["id"] not in taken | self.used
                and p.get("role_code") in (12, 13)
                and (self.e.level(p) or 9) <= 3
            ),
            key=lambda p: (self.hot(p), self.rate(p, "rp")),
            reverse=True,
        )
        if not pool:
            return []
        movable = [p for p in pen if p["id"] not in self.locked]
        worst = min(movable, key=self.rate, default=None)
        worst_now = min(
            (p for p in movable if self.struggling(p)), key=self.percentile, default=None
        )
        c = pool[0]
        if worst and self.rate(c, "rp") - self.rate(worst) >= UPGRADE["rp"]:
            out, call = worst, "Do it"
        elif worst_now and self.hot(c) and self.rate(c, "rp") >= self.rate(worst_now) - 0.3:
            out, call = worst_now, "Worth a look"
        else:
            return []
        self.used.add(c["id"])
        chain = [f"Call up {c['name']} from {self.where(c)}.", self.send_down(out)]
        chain += self.paperwork(c)
        why = (
            f"{c['name']} is a better arm than {out['name']} right now."
            if call == "Do it"
            else f"{c['name']} is dominating his league while {out['name']} is getting hit."
        )
        return [
            self.move(
                "Bullpen",
                call,
                f"{c['name']} for {out['name']}",
                why,
                max(self.rate(c, "rp") - self.rate(out), 0),
                chain,
                [self.card(c, "rp", "Call up"), self.card(out, "rp", "Our reliever")],
            )
        ]

    def lineup(self):
        moves = []
        lineup = self.roster["lineup"]
        bench = self.roster["bench"]
        playing = {x["player"]["id"] for x in lineup if x["player"]}
        hitters = [
            p
            for p in self.org
            if p["kind"] == "bat" and p["id"] not in playing and (self.e.level(p) or 9) <= 3
        ]
        for slot in lineup:
            pos, incumbent = slot["position"], slot["player"]
            if not incumbent or incumbent["id"] in self.locked or pos == "DH":
                continue
            fits = sorted(
                (p for p in hitters if p["id"] not in self.used and self.can_play(p, pos)),
                key=lambda p: (self.hot(p), self.rate(p)),
                reverse=True,
            )
            if not fits:
                continue
            best_by_projection = max(fits, key=self.rate)
            if self.rate(best_by_projection) - self.rate(incumbent) >= UPGRADE["bat"]:
                c, call = best_by_projection, "Do it"
            elif (
                self.hot(fits[0])
                and self.struggling(incumbent)
                and self.rate(fits[0]) >= self.rate(incumbent) - 1.0
            ):
                c, call = fits[0], "Worth a look"
            elif incumbent.get("day_to_day"):
                c = max(fits, key=self.rate)
                self.used.add(c["id"])
                moves.append(
                    self.move(
                        "Lineup",
                        "Be ready",
                        f"If {incumbent['name']} lands on the IL, {c['name']} plays {pos}",
                        f"{incumbent['name']} is day-to-day; {c['name']} is our best option at {pos}.",
                        0,
                        [f"Place {incumbent['name']} on the IL."]
                        + (
                            [f"{c['name']} starts at {pos}."]
                            if any(b["id"] == c["id"] for b in bench)
                            else [f"Call up {c['name']} from {self.where(c)} to play {pos}."]
                            + self.paperwork(c)
                        ),
                        [
                            self.card(c, "bat", "Next man up"),
                            self.card(incumbent, "bat", "Day-to-day"),
                        ],
                    )
                )
                continue
            else:
                continue
            self.used.add(c["id"])
            on_bench = any(b["id"] == c["id"] for b in bench)
            if on_bench:
                chain = [
                    f"Start {c['name']} at {pos} every day.",
                    f"{incumbent['name']} moves to the bench.",
                ]
            else:
                chain = [f"Call up {c['name']} from {self.where(c)} to play {pos} every day."]
                weakest_bench = min(
                    (b for b in bench if b["id"] not in self.locked), key=self.rate, default=None
                )
                if weakest_bench and self.rate(incumbent) > self.rate(weakest_bench):
                    chain.append(f"{incumbent['name']} moves to the bench.")
                    chain += self.arrival_steps(c, [weakest_bench])
                else:
                    chain.append(self.send_down(incumbent))
                    chain += self.paperwork(c)
            why = (
                f"{c['name']} projects better than {incumbent['name']} at {pos}."
                if call == "Do it"
                else f"{c['name']} is raking in {self.where(c)} while {incumbent['name']} is struggling. "
                f"His ratings say {self.rate(c):.1f} wins a season against {self.rate(incumbent):.1f}, "
                "so this is a bet on the results."
            )
            moves.append(
                self.move(
                    "Lineup",
                    call,
                    f"{c['name']} at {pos} over {incumbent['name']}",
                    why,
                    max(self.rate(c) - self.rate(incumbent), 0),
                    chain,
                    [self.card(c, "bat", "Candidate"), self.card(incumbent, "bat", f"Our {pos}")],
                )
            )
        return moves

    def depth(self):
        """Who's next in line, once per player, with where he could help."""
        notes = []
        lineup = {x["position"]: x["player"] for x in self.roster["lineup"] if x["player"]}
        for p in sorted(self.org, key=self.rate, reverse=True):
            if (
                p["id"] in self.used
                or (self.e.level(p) or 9) in (1, 9)
                or (self.e.level(p) or 9) > 3
            ):
                continue
            if not (self.hot(p) or (p["kind"] == "pit" and self.rate(p, "sp") >= 1.5)):
                continue
            if p["kind"] == "pit":
                role = "sp" if p.get("role_code") == 11 else "rp"
                spot = "rotation" if role == "sp" else "bullpen"
                notes.append(
                    {
                        "group": spot,
                        "headline": f"{p['name']} is next in line for the {spot}.",
                        "players": [self.card(p, role, "Depth")],
                    }
                )
            else:
                spots = [pos for pos in lineup if pos != "DH" and self.can_play(p, pos)]
                if not spots:
                    continue
                notes.append(
                    {
                        "group": "lineup",
                        "headline": f"{p['name']} can cover {', '.join(spots)} if we need a bat.",
                        "players": [self.card(p, "bat", "Depth")],
                    }
                )
            if len(notes) >= 4:
                break
        return notes

    def move(self, kind, call, title, why, gain_per_season, chain, comps):
        return {
            "kind": kind,
            "call": call,
            "title": title,
            "why": why,
            "gain_per_season": round(gain_per_season, 1),
            "gain_rest_of_year": round(gain_per_season * self.e.season_left, 1),
            "chain": [c for c in chain if c],
            "comps": comps,
        }

    def all(self):
        moves = self.rotation() + self.bullpen() + self.lineup()
        order = {"Do it": 0, "Worth a look": 1, "Be ready": 2}
        moves.sort(key=lambda m: (order[m["call"]], -m["gain_rest_of_year"]))
        moves = moves[:MAX_MOVES]
        changes = [m for m in moves if m["call"] != "Be ready"]
        return {
            "moves": moves,
            "depth": self.depth(),
            "headline": (
                f"{len(changes)} move{'s' if len(changes) != 1 else ''} worth making. Start with: {changes[0]['title']}."
                if changes
                else "No changes needed: the best players we have are already playing."
            ),
            "season_left": round(self.e.season_left, 2),
        }


_SEASONS = {}


def season_index(d):
    """Every player's lines this year, ranked within their league: {(kind, id): [rows]}.
    Same math as the MLB-readiness desk (FIP for pitchers, OPS for hitters), loaded in two
    queries instead of one per player."""
    if d.sid in _SEASONS:
        return _SEASONS[d.sid]
    levels = {t["league_id"]: t["level"] for t in d.teams.values() if not t.get("allstar_team")}
    index = {}
    con = connect(d.sid)
    try:
        for kind, table, fields, exposure, threshold in (
            ("bat", "bat_seasons", BAT_FIELDS, "pa", 100),
            ("pit", "pit_seasons", PIT_FIELDS, "outs", 90),
        ):
            by_league = {}
            for r in records(
                con, f"select * from {table} where year=? and {exposure} > 0", [d.year]
            ):
                by_league.setdefault(r["league_id"], []).append(r)
            for league_id, rows in by_league.items():
                base = combine(rows, fields)
                constant = fip_constant(base) if kind == "pit" else None
                calc = (lambda row: pitching(row, constant)) if kind == "pit" else batting
                metric = "fip" if kind == "pit" else "ops"
                peers = [
                    v
                    for v in (calc(r)[metric] for r in rows if number(r.get(exposure)) >= threshold)
                    if v is not None
                ]
                ranked = [-v for v in peers] if kind == "pit" else peers
                for r in rows:
                    m = calc(r)
                    qualified = number(r.get(exposure)) >= threshold
                    value = m[metric]
                    pct = (
                        percentile(ranked, -value if kind == "pit" else value)["percentile"]
                        if qualified and value is not None
                        else None
                    )
                    index.setdefault((kind, r["player_id"]), []).append(
                        {
                            **m,
                            "year": r["year"],
                            "league_id": league_id,
                            "league": d.leagues.get(league_id, {}).get("abbr", str(league_id)),
                            "level": levels.get(league_id, 99),
                            "qualified": qualified,
                            "quality_percentile": pct,
                        }
                    )
    finally:
        con.close()
    _SEASONS.clear()
    _SEASONS[d.sid] = index
    return index


def stat_text(p, s, short=False):
    """'3.79 ERA, 3.07 FIP, 26% K, 5% BB in 111.2 IP (AAA; top 3% of the IL)'."""
    if p["kind"] == "pit":
        text = (
            f"{s['era']:.2f} ERA in {s['ip_display']} IP"
            if short
            else f"{s['era']:.2f} ERA, {s['fip']:.2f} FIP, {s['k_pct']:.0%} K, {s['bb_pct']:.0%} BB "
            f"in {s['ip_display']} IP"
        )
    else:
        text = (
            f"{rate3(s['ops'])} OPS in {int(s['pa'])} PA"
            if short
            else f"{rate3(s['avg'])}/{rate3(s['obp'])}/{rate3(s['slg'])}, {int(s['hr'])} HR, "
            f"{int(s['sb'])} SB in {int(s['pa'])} PA"
        )
    if short:
        return text
    rank = league_rank(s)
    return f"{text} ({LEVELS.get(s['level'], s['league'])}{'; ' + rank if rank else ''})"


def league_rank(s):
    """'top 3% of the IL' from a season row's within-league percentile."""
    pct = s.get("quality_percentile")
    if pct is None or not s.get("qualified"):
        return ""
    league = s.get("league") or "league"
    if pct >= 90:
        return f"top {max(1, round(100 - pct))}% of the {league}"
    if pct >= 60:
        return f"better than {round(pct)}% of the {league}"
    if pct >= 40:
        return f"about average in the {league}"
    return f"bottom {max(1, round(pct))}% of the {league}"


def rate3(x):
    return f"{x:.3f}".lstrip("0") if x is not None else "---"


def suggested_moves(office):
    return Moves(office).all()
