"""What a player is worth to us, in dollars, over the years we control him.

Value = (projected WAR x what a win costs in this league) - salary, summed over every season
we control the player, discounted 5% a year. Everything is calibrated from the save itself
each export: the rating-to-WAR lines, the price of a win, the aging curve and how fast
young players close the gap to their potential. With scouting off, OOTP ratings are the
truth the sim plays from, so projections start from ratings rather than past stats.
"""

import statistics
import threading

from analytics import number
from storage import connect, records

DISCOUNT = 0.95
HORIZON = 12  # seasons
FULL_TIME = {"bat": 600, "sp": 170, "rp": 60}  # PA or IP that a WAR rate is expressed per
# Starting points if a save is too small to calibrate (fit on the 2026 MLB save, July).
FALLBACK_LINES = {"bat": (-5.63, 0.147), "sp": (-5.12, 0.138), "rp": (-1.52, 0.040)}
FALLBACK_DOLLARS_PER_WAR = 7_000_000
# Chance a prospect grows into his potential, by level. Judgment calls until we have
# several seasons of exports to measure them; MLB means a young big leaguer still developing.
DEVELOPS = {1: 0.85, 2: 0.75, 3: 0.6, 4: 0.45, 6: 0.3}
DEVELOPS_OTHER = 0.25
FALLBACK_ARBITRATION = {3: 0.12, 4: 0.26, 5: 0.36}  # share of market value; 2026 MLB save
DEBUT_WAR = 1.0  # a minor leaguer is projected into the majors once he'd be worth this

_CACHE = {}
_LOCK = threading.Lock()


def fit_line(points):
    """Least-squares line (intercept, slope) through (x, y) points."""
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    slope = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x in xs)
    return my - slope * mx, slope


def development_curve(rows):
    """Share of potential reached by age, from (age, oa, pot) rows. Never decreases; 1.0 at 26+."""
    by_age = {}
    for age, oa, pot in rows:
        if pot > 0:
            by_age.setdefault(int(age), []).append(oa / pot)
    curve, best = {}, 0.0
    for age in range(15, 26):
        if len(by_age.get(age, [])) >= 30:
            best = max(best, min(1.0, statistics.mean(by_age[age])))
        curve[age] = best
    first = next((v for v in curve.values() if v), 0.6)
    return {age: (v or first) for age, v in curve.items()}


def aging_curve(rows):
    """Weighted change in WAR rate from one season to the next, by age (delta method).

    rows: (age, change_in_war_rate, weight). Ages with thin samples borrow their neighbors.
    """
    by_age = {}
    for age, change, weight in rows:
        by_age.setdefault(int(age), []).append((change, weight))
    raw = {
        age: sum(c * w for c, w in v) / sum(w for _, w in v)
        for age, v in by_age.items()
        if len(v) >= 30 and sum(w for _, w in v) > 0
    }
    if not raw:
        return {}
    curve = {}
    for age in range(min(raw), max(raw) + 1):
        near = [raw[a] for a in (age - 1, age, age + 1) if a in raw]
        curve[age] = statistics.mean(near) if near else curve.get(age - 1, 0.0)
    return curve


def progress(curve, age_now, age_then):
    """How much of the remaining gap to potential a player closes between two ages."""
    if age_then <= age_now:
        return 0.0
    now = curve.get(min(age_now, 25), 1.0) if age_now < 26 else 1.0
    then = curve.get(min(age_then, 25), 1.0) if age_then < 26 else 1.0
    return 1.0 if now >= 1.0 else max(0.0, min(1.0, (then - now) / (1.0 - now)))


class ValueEngine:
    def __init__(self, d):
        self.d = d
        self.year = d.year
        con = connect(d.sid)
        try:
            self.lines = self._fit_lines(con)
            self.aging = {
                "bat": aging_curve(self._aging_rows(con, "bat")),
                "pit": aging_curve(self._aging_rows(con, "pit")),
            }
            self.development = development_curve(
                (r["age"], number(r["oa"]), number(r["pot"]))
                for r in records(
                    con,
                    "select p.age, v.oa, v.pot from players p join players_value v using(player_id)"
                    " where p.retired=0",
                )
            )
            team = records(con, "select g from team_record where team_id=?", [d.team])
            played = number(team[0]["g"]) if team else 0
            self.season_left = max(0.0, min(1.0, 1 - played / 162))
            mins = [
                number(r["salary0"])
                for r in records(
                    con,
                    "select c.salary0 from players_contract c join players p using(player_id)"
                    " where p.league_id=? and c.salary0 >= 500000",
                    [d.league],
                )
            ]
            self.league_min = min(mins) if mins else 740_000
            self.recent = self._recent_stats(con)
            self.dollars_per_war = self._price_of_a_win(con)
            self.arbitration = self._arbitration_shares(con)
        finally:
            con.close()

    # ---- calibration -------------------------------------------------------------------

    def _fit_lines(self, con):
        y, lg = self.year, self.d.league
        bat = records(
            con,
            "with b as (select player_id, sum(pa) pa, sum(war) war from players_career_batting_stats"
            " where league_id=? and level_id=1 and split_id=1 and year in (?, ?) group by 1)"
            " select v.oa, b.war / b.pa * 600 as rate from b join players_value v using(player_id)"
            " join players p using(player_id) where b.pa >= 300 and p.position <> 1",
            [lg, y, y - 1],
        )
        pit = records(
            con,
            "with s as (select player_id, sum(outs) / 3.0 ip, sum(war) war, sum(gs) gs, sum(g) g"
            " from players_career_pitching_stats where league_id=? and level_id=1 and split_id=1"
            " and year in (?, ?) group by 1)"
            " select v.oa, s.war / s.ip as rate, s.gs, s.g from s join players_value v using(player_id)"
            " where s.ip >= 60",
            [lg, y, y - 1],
        )
        samples = {
            "bat": [(number(r["oa"]), number(r["rate"])) for r in bat],
            "sp": [
                (number(r["oa"]), number(r["rate"]) * 170) for r in pit if r["gs"] >= 0.6 * r["g"]
            ],
            "rp": [
                (number(r["oa"]), number(r["rate"]) * 60) for r in pit if r["gs"] < 0.2 * r["g"]
            ],
        }
        return {
            role: fit_line(points) if len(points) >= 40 else FALLBACK_LINES[role]
            for role, points in samples.items()
        }

    def _aging_rows(self, con, kind):
        table = "players_career_batting_stats" if kind == "bat" else "players_career_pitching_stats"
        exposure = "pa" if kind == "bat" else "outs / 3.0"
        scale, minimum = (600, 250) if kind == "bat" else (170, 50)
        rows = records(
            con,
            f"with s as (select player_id, year, sum({exposure}) x, sum(war) war from {table}"
            " where league_id=? and level_id=1 and split_id=1 and year < ? group by 1, 2"
            f" having sum({exposure}) >= {minimum})"
            " select s1.year - year(p.date_of_birth) as age,"
            f" (s2.war / s2.x - s1.war / s1.x) * {scale} as change, least(s1.x, s2.x) as weight"
            " from s s1 join s s2 on s1.player_id = s2.player_id and s2.year = s1.year + 1"
            " join players p on p.player_id = s1.player_id",
            [self.d.league, self.year],
        )
        return [(r["age"], number(r["change"]), number(r["weight"])) for r in rows]

    def _recent_stats(self, con):
        """MLB plate appearances, innings and WAR over this season and last, per player."""
        recent = {}
        y, lg = self.year, self.d.league
        for r in records(
            con,
            "select player_id, sum(pa) pa, sum(war) war from players_career_batting_stats"
            " where league_id=? and level_id=1 and split_id=1 and year in (?, ?) group by 1",
            [lg, y, y - 1],
        ):
            recent[r["player_id"]] = {"pa": number(r["pa"]), "bat_war": number(r["war"])}
        for r in records(
            con,
            "select player_id, sum(outs) / 3.0 ip, sum(war) war from players_career_pitching_stats"
            " where league_id=? and level_id=1 and split_id=1 and year in (?, ?) group by 1",
            [lg, y, y - 1],
        ):
            recent.setdefault(r["player_id"], {}).update(
                ip=number(r["ip"]), pit_war=number(r["war"])
            )
        return recent

    def current_rate(self, p):
        """Full-season WAR rate today: ratings, blended with real MLB results as they pile up.

        Two full seasons of results count for half. Two-way players add their pitching.
        """
        role = self.role(p)
        from_ratings = self.war_rate(role, self.rating(p)[0])
        s = self.recent.get(p["id"], {})
        if role == "bat":
            seen, per, war, trust = s.get("pa", 0), 600, s.get("bat_war", 0), 1200
        else:
            seen, war = s.get("ip", 0), s.get("pit_war", 0)
            per, trust = (170, 340) if role == "sp" else (60, 120)
        rate = from_ratings
        if seen:
            from_results = war / seen * per
            rate = (from_results * seen + from_ratings * trust) / (seen + trust)
        if role == "bat" and s.get("ip", 0) >= 50:
            seasons_seen = 1 + (1 - self.season_left)
            rate += s.get("pit_war", 0) / seasons_seen
        return rate

    def _arbitration_shares(self, con):
        """What arbitration actually pays here: salary as a share of market value, by service year."""
        rows = records(
            con,
            "select c.player_id, c.salary0, r.mlb_service_years svc from players_contract c"
            " join players_roster_status r using(player_id) join players p using(player_id)"
            " where p.league_id=? and c.years=1 and r.mlb_service_years between 3 and 5",
            [self.d.league],
        )
        shares = {}
        for r in rows:
            p = self.d.by_id.get(r["player_id"])
            war = self.current_rate(p) if p else 0
            if war >= 1.0 and number(r["salary0"]) > self.league_min * 1.05:
                shares.setdefault(int(r["svc"]), []).append(
                    number(r["salary0"]) / (war * self.dollars_per_war)
                )
        return {
            year: statistics.median(shares[year]) if len(shares.get(year, [])) >= 10 else fallback
            for year, fallback in FALLBACK_ARBITRATION.items()
        }

    def _price_of_a_win(self, con):
        """Median salary per projected win among veterans signed to multi-year deals."""
        vets = records(
            con,
            "select p.player_id, c.salary0 from players p join players_contract c using(player_id)"
            " join players_roster_status r using(player_id)"
            " where p.league_id=? and r.mlb_service_years >= 6 and c.years >= 2 and c.salary0 >= 5000000",
            [self.d.league],
        )
        ratios = []
        for r in vets:
            p = self.d.by_id.get(r["player_id"])
            if not p:
                continue
            war = self.current_rate(p)
            if war >= 1.0:
                ratios.append(number(r["salary0"]) / war)
        return statistics.median(ratios) if len(ratios) >= 30 else FALLBACK_DOLLARS_PER_WAR

    # ---- player facts --------------------------------------------------------------------

    def role(self, p):
        if p["kind"] == "bat":
            return "bat"
        return "sp" if p.get("role_code") == 11 else "rp"

    def rating(self, p):
        v = self.d.ratings["players_value"].get(p["id"], {})
        oa = number(v.get("oa"))
        return oa, max(oa, number(v.get("pot")))

    def level(self, p):
        if p["free_agent"] or not p["team_id"]:
            return 1 if p["service_years"] else None
        return int(number(self.d.teams.get(p["team_id"], {}).get("level"), 0)) or None

    def war_rate(self, role, rating):
        intercept, slope = self.lines[role]
        return intercept + slope * rating

    def aged(self, role, rate, age_from, age_to):
        """Apply the league's aging curve from 26 on (development before that comes from potential)."""
        curve = self.aging["bat" if role == "bat" else "pit"]
        if not curve:
            return rate
        scale = 1.0 if role != "rp" else 60 / 170
        last = curve[max(curve)]
        for age in range(max(age_from, 26), age_to):
            rate += curve.get(age, last if age > max(curve) else 0.0) * scale
        return rate

    # ---- the valuation -------------------------------------------------------------------

    def path(self, p, develops):
        """Season-by-season projection for one scenario (develops into potential or not)."""
        d, role = self.d, self.role(p)
        oa, pot = self.rating(p)
        level = self.level(p)
        age = int(number(p["age"]))
        service = int(number(p["service_years"]))
        in_majors = level == 1
        contract_end = max(p["salaries"]) if p["salaries"] else None
        today = self.current_rate(p)
        # A veteran on a minor-league deal (off the 40-man, six-plus pro seasons) is a minor-league
        # free agent after this season, not ours for years.
        pro_years = number(self.d.roster.get(p["id"], {}).get("pro_service_years"))
        minor_league_deal = not in_majors and not p.get("secondary") and pro_years >= 6
        debut, seasons = None, []
        for i in range(HORIZON):
            if minor_league_deal and i > 0:
                break
            year = self.year + i
            age_then = age + i
            rating = oa + (pot - oa) * progress(self.development, age, age_then) if develops else oa
            growth = self.war_rate(role, rating) - self.war_rate(role, oa)
            rate = self.aged(role, today + growth, age, age_then)
            if not in_majors and debut is None and rate >= DEBUT_WAR:
                debut = year
            mlb = in_majors or debut is not None
            # Years of team control: the contract, or six MLB seasons for younger players.
            years_in = service + i if in_majors else service + (year - debut) if debut else 0
            controlled_by_service = years_in < 6
            signed = year in p["salaries"]
            if not signed and not (controlled_by_service and not p["free_agent"]):
                break
            full_war = max(0.0, rate) if mlb else 0.0
            war = full_war * (self.season_left if i == 0 else 1.0)
            market = war * self.dollars_per_war
            if signed:
                salary, status = p["salaries"][year], "signed"
            elif not mlb:
                salary, status = 0.0, "minors"
            else:
                share = self.arbitration.get(years_in)
                if share:
                    full = full_war * self.dollars_per_war
                    salary, status = max(self.league_min, share * full), "arbitration (est.)"
                else:
                    salary, status = self.league_min, "pre-arbitration"
                if full_war * self.dollars_per_war < salary:
                    break  # not guaranteed and not worth it: we'd non-tender or release him
            full_salary = salary
            if i == 0:
                salary *= self.season_left
            seasons.append(
                {
                    "year": year,
                    "age": age_then,
                    "rating": round(rating, 1),
                    "war": round(war, 2),
                    "full_season_war": round(full_war, 2),
                    "salary": round(salary),
                    "full_season_salary": round(full_salary),
                    "market": round(market),
                    "surplus": round(market - salary),
                    "status": status,
                    "weight": DISCOUNT**i,
                }
            )
            if contract_end and year >= contract_end and not controlled_by_service:
                break
        return seasons

    def chance_develops(self, p):
        """1.0 for finished players; otherwise the odds a young player grows into his potential."""
        oa, pot = self.rating(p)
        if int(number(p["age"])) >= 26 or pot <= oa:
            return 1.0
        level = self.level(p)
        return DEVELOPS.get(level, DEVELOPS_OTHER) if level else DEVELOPS_OTHER

    def forecast(self, p, last_year):
        """Full-season WAR each year through last_year, ignoring who controls him (for signings
        and extensions). Young players are weighted by their chance to develop."""
        role, (oa, pot) = self.role(p), self.rating(p)
        age, today, chance = int(number(p["age"])), self.current_rate(p), self.chance_develops(p)
        seasons = []
        for i in range(max(0, last_year - self.year + 1)):
            grown = oa + (pot - oa) * progress(self.development, age, age + i)
            rates = [
                self.aged(
                    role, today + self.war_rate(role, r) - self.war_rate(role, oa), age, age + i
                )
                for r in (grown, oa)
            ]
            war = max(0.0, chance * rates[0] + (1 - chance) * rates[1])
            seasons.append({"year": self.year + i, "age": age + i, "war": round(war, 2)})
        return seasons

    def player(self, p):
        oa, pot = self.rating(p)
        level = self.level(p)
        if p["free_agent"]:
            war = max(0.0, self.current_rate(p))
            return {
                "id": p["id"],
                "name": p["name"],
                "free_agent": True,
                "peak_war": round(war, 1),
                "asking_value": round(war * self.dollars_per_war, -5),
                "summary": f"Free agent. Projects around {war:.1f} wins a season; "
                f"that's worth about {dollars(war * self.dollars_per_war)} a year on the market.",
            }
        chance = self.chance_develops(p)
        up = self.path(p, True)
        flat = self.path(p, False) if chance < 1 else up

        def total(seasons, key):
            return sum(s[key] * s["weight"] for s in seasons)

        value = chance * total(up, "surplus") + (1 - chance) * total(flat, "surplus")
        market = chance * total(up, "market") + (1 - chance) * total(flat, "market")
        cost = chance * total(up, "salary") + (1 - chance) * total(flat, "salary")
        mlb_seasons = [s for s in up if s["status"] != "minors"]
        best = max(up, key=lambda s: s["full_season_war"], default=None)
        peak = best["full_season_war"] if best else 0.0
        result = {
            "id": p["id"],
            "name": p["name"],
            "value": round(value, -5),
            "market_value": round(market, -5),
            "salary_owed": round(cost, -5),
            "war_this_season": up[0]["war"] if up else 0.0,
            "peak_war": round(peak, 1),
            "peak_year": best["year"] if best else None,
            "control_through": up[-1]["year"] if up else None,
            "chance_develops": round(chance, 2),
            "seasons": [{k: v for k, v in s.items() if k != "weight"} for s in up],
            "free_agent": p["free_agent"],
            "age": int(number(p["age"])),
        }
        result["risk"] = (
            "Proven" if chance == 1 else "Still developing" if level == 1 else "Prospect"
        )
        result["summary"] = self.summary(p, result, mlb_seasons)
        return result

    def summary(self, p, v, mlb_seasons):
        """One plain-English line, the way an assistant GM would say it."""
        if not v["seasons"]:
            return "Replaceable. He doesn't project to be worth a big-league salary, so he carries no trade value."
        if v["risk"] != "Prospect" and all(s["status"] == "minors" for s in v["seasons"]):
            return "Minor-league depth: no real trade value."
        money = dollars(v["value"])
        through = v["control_through"]
        wins = f"{v['peak_war']:.1f}-win"
        if v["risk"] == "Prospect":
            first = next((s["year"] for s in v["seasons"] if s["status"] != "minors"), None)
            if not first:
                return f"Long shot. Doesn't project as a big leaguer yet; worth about {money} as a lottery ticket."
            ready = "Ready now" if first == self.year else f"Big-league ready around {first}"
            return (
                f"Prospect worth about {money}. {ready}; if he develops "
                f"({v['chance_develops']:.0%} chance) he's a {wins} player by {v['peak_year']}."
            )
        if v["value"] < 0:
            return f"Costs us about {dollars(-v['value'])} more than he's worth through {through}."
        if through == self.year:
            return f"Worth about {money} to us for the rest of {through}, then he can walk as a free agent."
        avg = statistics.mean(s["full_season_salary"] for s in mlb_seasons) if mlb_seasons else 0
        return f"Worth about {money} to us: a {wins} player, ours through {through} at about {dollars(avg)} a year."


def dollars(amount):
    """$177M, $5.2M, $740K; negatives as -$5.0M."""
    amount = float(amount)
    sign, amount = ("-" if amount < 0 else ""), abs(amount)
    if amount >= 10_000_000:
        return f"{sign}${amount / 1_000_000:.0f}M"
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.1f}M"
    return f"{sign}${amount / 1000:.0f}K"


def value_engine(d):
    with _LOCK:
        if d.sid not in _CACHE:
            _CACHE[d.sid] = ValueEngine(d)
        return _CACHE[d.sid]
