"""Transparent OOTP assignment and workload suggestions, never game commands."""

from analytics import number, pitching


def pitch_limit(stamina, history=None, age=26, unavailable=False):
    if unavailable:
        return None, [
            "Do not schedule a start until availability and clearance are confirmed in OOTP."
        ]
    if not 1 <= number(stamina) <= 10:
        return None, ["Stamina is missing or outside the configured 1-10 scale; review manually."]
    cap = min(110, 70 + 5 * number(stamina))
    notes = [f"Stamina {number(stamina):g}/10 sets an initial {int(cap)}-pitch planning cap."]
    h = history or {}
    g = number(h.get("g"))
    gs = number(h.get("gs"))
    ip = number(h.get("outs")) / 3
    if gs >= 5 and g and gs / g >= 0.8:
        if number(h.get("pi")) > 0:
            average = number(h["pi"]) / g
            bound = 5 * round((average + 5) / 5)
            cap = min(cap, max(75, bound))
            notes.append(
                f"{h.get('year','Recent season')}: {average:.1f} pitches per appearance across {int(g)} appearances ({int(gs)} starts). Mostly-starting usage supports this workload reference; it is not an exact pitches-per-start split."
            )
        if ip < 60:
            cap = min(cap, 85)
            notes.append(
                "Fewer than 60 MLB innings in the reference season: begin with a shorter workload."
            )
        elif ip < 100:
            cap = min(cap, 90)
            notes.append(
                "Fewer than 100 MLB innings in the reference season: keep the initial cap conservative."
            )
    else:
        cap = min(cap, 85)
        notes.append(
            "No recent established MLB starting workload: use a trial cap and review actual minor-league workload and development before increasing it."
        )
    if age < 23:
        cap = min(cap, 90)
        notes.append(
            "Young starter: prioritize a sustainable progression and regular recovery checks."
        )
    return int(cap), notes


def split_quality(r, side):
    vs = [
        (number(r.get("pitching_ratings_" + side + "_" + k)), w)
        for k, w in [("stuff", 0.4), ("movement", 0.3), ("control", 0.3)]
    ]
    return round(sum(v * w for v, w in vs), 2) if all(1 <= v <= 10 for v, w in vs) else None


def bullpen_assignments(rows, philosophy="Blended"):
    """Each selected pitcher gets one primary role; locked membership is unchanged."""
    usable = [r for r in rows if r["quality"] is not None and not r["unavailable"]]
    ordered = sorted(usable, key=lambda r: (r["quality"], r["evidence_ip"]), reverse=True)
    assigned = {}
    if ordered:
        best = ordered.pop(0)
        stopper = (
            philosophy == "Analytics-led"
            and best["stamina"] >= 5
            and best["quality"] >= 6
            and best["vsr"] is not None
            and best["vsl"] is not None
            and min(best["vsr"], best["vsl"]) >= 5.5
        )
        assigned[best["id"]] = (
            "Stopper" if stopper else "Closer",
            None if stopper else "9th or later",
            (
                "Use the best available relief tools in the biggest late-game situations."
                if stopper
                else "The strongest selected relief option gets the ninth-inning job; save totals do not determine this choice."
            ),
        )
        if ordered:
            setup = ordered.pop(0)
            assigned[setup["id"]] = (
                "Setup",
                "8th or later",
                "The next-strongest selected arm bridges the game to the primary late-inning pitcher.",
            )
        long = [r for r in ordered if r["stamina"] >= 5 and r["starter_qualified"]]
        if long:
            p = max(long, key=lambda r: (r["stamina"], r["quality"]))
            ordered.remove(p)
            assigned[p["id"]] = (
                "Long Relief",
                "Normal Usage",
                "Stamina and starting evidence support covering an early exit; Emergency SP is a useful secondary role.",
            )
        seventh_used = False
        for p in ordered:
            gap = abs(p["vsr"] - p["vsl"]) if p["vsr"] is not None and p["vsl"] is not None else 0
            if gap >= 1 and max(p["vsr"], p["vsl"]) >= 5:
                assigned[p["id"]] = (
                    "Specialist",
                    "Normal Usage",
                    "A clear rated handedness advantage supports a matchup role. Check the league minimum-batters rule before assuming a one-batter appearance.",
                )
            elif p["quality"] >= 5.5 and not seventh_used:
                assigned[p["id"]] = (
                    "Setup",
                    "7th or later",
                    "A third reliable arm handles the seventh inning and protects the eighth-inning option.",
                )
                seventh_used = True
            else:
                assigned[p["id"]] = (
                    "Middle Relief",
                    (
                        "Avoid high leverage"
                        if p["quality"] < 4.5
                        else "Use more often" if p["quality"] >= 5 else "Normal Usage"
                    ),
                    (
                        "Protect this arm from the most difficult late-game situations."
                        if p["quality"] < 4.5
                        else "Cover the middle innings and preserve the late-game pair; matchup and rest can change daily usage."
                    ),
                )
    out = []
    for p in rows:
        role, usage, reason = assigned.get(
            p["id"],
            (
                "None specified",
                None,
                "Availability or current ratings need review before assigning a competitive role.",
            ),
        )
        notes = list(p["notes"])
        secondary = (
            "Emergency SP"
            if role == "Long Relief"
            else (
                "Closer"
                if role == "Setup" and any(v[0] == "Stopper" for v in assigned.values())
                else "None specified"
            )
        )
        alternative = (
            "Stopper"
            if role == "Closer" and p["stamina"] >= 5
            else "Closer" if role == "Stopper" else None
        )
        if role == "Stopper":
            notes.append(
                "Use the strongest available arm when the game is in danger from the seventh onward, rather than holding him for a save. Confirm the exact inning/lead trigger in the Stopper usage menu; it was not shown in the supplied screenshots."
            )
        if role == "Specialist":
            notes.append(
                "Preferred matchup: "
                + ("right-handed hitters" if p["vsr"] > p["vsl"] else "left-handed hitters")
                + ". These are ratings, not observed split results."
            )
        out.append(
            {
                **p,
                "role": role,
                "usage": usage,
                "secondary_role": secondary,
                "alternative": alternative,
                "reason": reason,
                "notes": notes,
            }
        )
    return out


def pitching_recommendations(office, rotation, bullpen):
    d = office.d
    starters = []
    relief = []

    def evidence(p):
        raw = d.raw.get(p["id"], {})
        r = d.ratings["players_pitching"].get(p["id"], {})
        hist = sorted(
            [
                h
                for h in d.hist["pit"].get(p["id"], [])
                if d.year - 2 <= h["year"] < d.year and number(h.get("g")) > 0
            ],
            key=lambda h: h["year"],
            reverse=True,
        )
        h = hist[0] if hist else None
        stamina = number(r.get("pitching_ratings_misc_stamina"))
        pitches = sum(
            1
            for k, v in r.items()
            if k.startswith("pitching_ratings_pitches_")
            and "talent" not in k
            and 4 <= number(v) <= 10
        )
        vsr = split_quality(r, "vsr")
        vsl = split_quality(r, "vsl")
        vals = [
            (number(r.get("pitching_ratings_overall_" + k)), w)
            for k, w in [("stuff", 0.4), ("movement", 0.3), ("control", 0.3)]
        ]
        quality = (
            round(sum(v * w for v, w in vals), 2) if all(1 <= v <= 10 for v, w in vals) else None
        )
        unavailable = bool(
            p["injured"] or p["on_dl"] or number(raw.get("dtd_injury_effect_throw")) > 0
        )
        fatigue = {
            k: raw.get(k)
            for k in [
                "fatigue_points",
                "fatigue_played_today",
                *("fatigue_pitches" + str(i) for i in range(6)),
            ]
        }
        notes = []
        if any(number(v) > 0 for v in fatigue.values()):
            notes.append(
                "The export contains recent-work or fatigue indicators. Confirm today’s rest/readiness in OOTP; raw values are not interpreted as a calibrated fatigue percentage."
            )
        if not hist:
            notes.append(
                "No recent MLB workload history; minor-league workload must be reviewed separately."
            )
        return {
            "id": p["id"],
            "stamina": stamina,
            "qualifying_pitches": pitches,
            "starter_qualified": stamina >= 5
            and (pitches >= 3 or bool(h and number(h.get("gs")) >= 0.5 * number(h.get("g")))),
            "quality": quality,
            "vsr": vsr,
            "vsl": vsl,
            "evidence_ip": round(number((h or {}).get("outs")) / 3, 1),
            "recorded": pitching(h, d.fip_c) if h else None,
            "history": h,
            "unavailable": unavailable,
            "fatigue": fatigue,
            "notes": notes,
        }

    for row in rotation:
        if not row["player"]:
            continue
        p = row["player"]
        e = evidence(p)
        cap, notes = pitch_limit(e["stamina"], e["history"], p["age"], e["unavailable"])
        warnings = e["notes"]
        if not e["starter_qualified"]:
            warnings.append(
                "Current stamina/repertoire or recent starting usage does not establish a normal starter role. Review this assignment; any GM lock remains binding."
            )
        notes.append(
            "Spring-training and rehab buildup are not established by these MLB season totals. Start lower if he is not fully stretched out, and recheck after each outing."
        )
        starters.append(
            {
                **e,
                "player": p,
                "slot": row["slot"],
                "pitch_count": cap,
                "review_range": {"low": max(60, cap - 10), "high": cap} if cap else None,
                "reason": "Begin at this cap, not a quota. Pull earlier for poor effectiveness, fatigue or matchup concerns.",
                "notes": notes + warnings,
                "exported_pitch_count": d.raw.get(p["id"], {}).get("strategy_pitch_count"),
            }
        )
    for row in bullpen:
        relief.append({**evidence(row["player"]), "player": row["player"], "locked": row["locked"]})
    assignments = bullpen_assignments(relief, office.b["philosophy"])
    coverage = []
    if not any(p["role"] == "Long Relief" for p in assignments):
        coverage.append(
            "No selected reliever has both the stamina and starting evidence for a dedicated Long Relief / Emergency SP role. Review internal swingman coverage before replacing a selected arm; do not assume every reliever can absorb an early starter exit."
        )
    if any(p["role"] == "Stopper" for p in assignments):
        coverage.append(
            "Stopper deployment can spend the best arm before the ninth. The Setup pitcher is the suggested closing fallback; verify secondary-role support and actual rest in OOTP."
        )
    return {
        "coverage_notes": coverage,
        "rotation": starters,
        "bullpen": assignments,
        "settings": {
            "rotation_size": "5-Man Rotation",
            "rotation_mode": "Strict, on occasion highest rested",
            "allow_sp_in_relief": "Only in Crucial Situations",
            "reason": "Keep regular recovery predictable; use a rested starter in relief only for a genuine critical need and account for his next scheduled start.",
        },
        "method": [
            "Recommendations use selected roster membership and preserve binding GM locks. They do not change OOTP settings.",
            "Relief priority uses 40% stuff, 30% movement and 30% control, with recent MLB innings breaking ties. Stamina, repertoire and rated handedness differences shape assignments; saves and reputation do not set the order. These fixed weights are a transparent heuristic, not calibrated leverage value.",
            "Analytics-led plans consider a Stopper when the best relief arm has stamina at least 5, overall current tools at least 6 and both rated splits at least 5.5. The actual Stopper usage menu must be checked before applying an inning/lead trigger. Other plans use a Closer and Setup pair.",
            "Initial starter cap = 70 + 5 × stamina, capped at 110; established starting workload, low prior-season innings and youth can lower it. Missing stamina or throwing availability produces no usable cap. No cap proves a safe workload or an optimal OOTP result.",
            "A pitch cap is a maximum planning threshold, not a target to reach. Reassess during early-season buildup, injury returns, short rest and schedule congestion. Fatigue export units and recent injury clearance are not inferred.",
            "The specific bullpen role names and displayed usage options match the supplied OOTP menus. Role-specific options, secondary-role combinations and manager overrides must still be checked in the game.",
        ],
    }
