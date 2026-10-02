"""User-entered owner priorities, annual archives and evidence-aware reviews."""

from analytics import number

CATEGORIES = [
    "Playoffs",
    "Position upgrade",
    "Popularity",
    "Chemistry",
    "Fan interest",
    "Championship window",
    "Other",
]
STATUSES = ["Not assessed", "In progress", "At risk", "Owner-confirmed complete", "Not met"]


def validate_goals(body):
    year = int(body.get("year", 0))
    if not 1800 <= year <= 3000:
        raise ValueError("Choose a valid season.")
    goals = body.get("goals", [])
    if not isinstance(goals, list) or len(goals) > 30:
        raise ValueError("Use at most 30 owner goals per season.")
    clean = []
    for i, g in enumerate(goals):
        title = str(g.get("title", "")).strip()
        category = g.get("category", "Other")
        status = g.get("status", "Not assessed")
        position = g.get("position", "")
        due = int(g.get("due_year") or year)
        if not title or len(title) > 1000:
            raise ValueError("Each goal needs a title of at most 1,000 characters.")
        if category not in CATEGORIES or status not in STATUSES:
            raise ValueError("Choose a supported goal category and status.")
        if position not in [
            "",
            "C",
            "1B",
            "2B",
            "3B",
            "SS",
            "LF",
            "CF",
            "RF",
            "DH",
            "SP",
            "RP",
            "P",
        ]:
            raise ValueError("Choose a supported position.")
        if not year <= due <= year + 20:
            raise ValueError("Goal deadline must be within the next 20 seasons.")
        clean.append(
            {
                "id": str(g.get("id") or f"goal-{i}")[:100],
                "title": title,
                "category": category,
                "status": status,
                "position": position,
                "due_year": due,
                "notes": str(g.get("notes", ""))[:5000],
            }
        )
    return year, {
        "owner": str(body.get("owner", ""))[:200],
        "letter": str(body.get("letter", ""))[:20000],
        "goals": clean,
    }


def owner_context(office):
    season = office.state.get("owner_goals", {}).get(str(office.d.year), {})
    goals = [
        g
        for y, s in office.state.get("owner_goals", {}).items()
        if int(y) <= office.d.year
        for g in s.get("goals", [])
        if int(g["due_year"]) >= office.d.year
        and g["status"] not in ["Owner-confirmed complete", "Not met"]
    ]
    implications = []
    for g in goals:
        cat = g["category"]
        text = {
            "Playoffs": "Favor credible improvements to the current MLB roster, while measuring playoff ambition against the unbiased forecast.",
            "Position upgrade": f"Review a real upgrade at {g.get('position') or 'the requested position'} against the incumbent, defense, splits, playing time and acquisition cost. A new name alone is not an upgrade.",
            "Popularity": "National popularity is a separate owner objective. Verify the OOTP popularity label; do not treat an expensive star as available or assume a guaranteed fan-interest gain.",
            "Chemistry": "Check the actual clubhouse report, leadership and disruption before a move. Personality or individual morale is not proof of team chemistry.",
            "Fan interest": "Track exported fan interest against the captured baseline. Winning or adding a player does not guarantee a specific increase.",
            "Championship window": f"Keep a championship path through {g['due_year']}: preserve useful control, sustainable payroll and a development pipeline.",
            "Other": "Include this priority in the decision alongside roster fit, cost and your saved constraints.",
        }[cat]
        implications.append(
            {
                "title": g["title"],
                "category": cat,
                "position": g.get("position", ""),
                "status": g["status"],
                "detail": text,
            }
        )
    return {
        "year": office.d.year,
        "owner": season.get("owner", ""),
        "goals": implications,
        "note": "Owner priorities inform review; they do not alter the independent win forecast, override player locks or certify that OOTP considers a goal completed.",
    }


def owner_board(office, year=None):
    d = office.d
    year = int(year or d.year)
    season = office.state.get("owner_goals", {}).get(str(year), {})
    baseline = season.get("baseline", {})
    financial = d.financials[d.team]
    fan = financial.get("fan_interest_visible")
    fan = financial.get("fan_interest") if fan is None else fan
    current_year = year == d.year
    start = baseline.get("fan_interest")
    delta = (
        number(fan) - number(start)
        if fan is not None and start is not None and current_year
        else None
    )
    evidence = {
        "fan_interest": fan if current_year else None,
        "baseline_fan_interest": start,
        "fan_change": delta,
        "baseline_date": baseline.get("game_date"),
        "baseline_2b": baseline.get("second_base"),
        "note": "Fan-interest change is an exported observation, not owner-confirmed completion. Chemistry, popularity labels, playoff completion and championship progress need the owner/game screen.",
    }
    return {
        "year": year,
        "years": sorted(office.state.get("owner_goals", {}), reverse=True),
        "season": season,
        "evidence": evidence,
        "context": owner_context(office) if current_year else None,
        "categories": CATEGORIES,
        "statuses": STATUSES,
    }


def capture_baseline(office):
    from storage import snapshots
    from department import department
    from readiness import team_view
    from frontoffice import Office

    d = office.d
    earlier = [
        m
        for m in snapshots(d.manifest.get("source_id"))
        if str(m.get("game_date", "")).startswith(str(d.year)) and m.get("league_id") == d.league
    ]
    if earlier:
        first = min(earlier, key=lambda m: (str(m["game_date"]), m["created_at"]))
        office = Office(team_view(department(first["id"]), d.team))
        d = office.d
    financial = d.financials[d.team]
    roster = office.roster()
    second = next((x["player"] for x in roster["lineup"] if x["position"] == "2B"), None)
    return {
        "snapshot": d.sid,
        "game_date": str(d.manifest["game_date"]),
        "fan_interest": financial.get("fan_interest_visible", financial.get("fan_interest")),
        "second_base": (
            {
                "id": second["id"],
                "name": second["name"],
                "grade": second["grade"],
                "summary": second["summary"],
            }
            if second
            else None
        ),
    }
