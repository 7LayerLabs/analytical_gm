"""Conservative acquisition screens: payroll is not trade price."""

from analytics import number


def market_context(p, value, ratings, defense, fa_service=6):
    oa = number(value.get("oa_rating"))
    pot = number(value.get("pot_rating"))
    young = p["age"] <= 28
    service = number(p.get("service_years"))
    controlled = not p["free_agent"] and service < fa_service
    prefix = "batting_ratings_talent_" if p["kind"] == "bat" else "pitching_ratings_talent_"
    keys = (
        ["contact", "gap", "power", "eye", "strikeouts"]
        if p["kind"] == "bat"
        else ["stuff", "movement", "control"]
    )
    tools = {k: ratings.get(prefix + k) for k in keys}
    valid = [number(v) for v in tools.values() if 1 <= number(v) <= 10]
    elite_upside = pot >= 8 or bool(valid and sum(valid) / len(valid) >= 7 and max(valid) >= 8)
    high_current = oa >= 8 or number(p.get("engine_percentile")) >= 90
    premium = not p["free_agent"] and (
        high_current
        or young
        and elite_upside
        or controlled
        and number(p.get("rating_component")) >= 6.5
    )
    best_defense = (
        max([number(defense.get("fielding_rating_pos" + str(i))) for i in range(2, 10)], default=0)
        if p["kind"] == "bat"
        else None
    )
    reasons = []
    if young and elite_upside:
        reasons.append(
            f"Age {p['age']} with premium upside; the selling club has a valuable long-term asset."
        )
    if high_current:
        reasons.append("High current MLB value makes a substantial trade return likely.")
    if controlled:
        reasons.append(
            f"Exported MLB service: {service:g} years, below the save’s {fa_service:g}-year free-agency threshold. A one-year salary entry does not establish one year of team control."
        )
    if best_defense and best_defense >= 7:
        reasons.append(
            f"Best currently rated position defense {best_defense:g}/10 adds value beyond offense."
        )
    if premium and controlled and not young:
        reasons.append(
            "Strong current tools plus remaining service-based control can make an established veteran expensive to acquire too."
        )
    if premium:
        reasons.append(
            "Expect a premium prospect/player package. Actual asking price and willingness to trade are not exported; no cheap-acquisition claim is supported."
        )
    elif p["free_agent"]:
        reasons.append(
            "Exported as a free agent. Asking salary, competing offers and willingness to sign require an OOTP inquiry."
        )
    else:
        reasons.append(
            "Trade availability and asking package are unknown. This is a player to inquire about if he addresses a real need."
        )
    return {
        "tier": (
            "Premium trade target"
            if premium
            else "Free-agent inquiry" if p["free_agent"] else "Trade inquiry"
        ),
        "premium": premium,
        "availability": (
            "Free-agent flag exported" if p["free_agent"] else "Trade availability unconfirmed"
        ),
        "reasons": reasons,
        "potential_tools": tools,
        "overall_current": oa or None,
        "overall_potential": pot or None,
        "best_defense": best_defense,
        "controlled": controlled,
        "price_known": False,
    }
