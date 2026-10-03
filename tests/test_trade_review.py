import unittest
from trade_review import trade_verdict, owner_goal_signal


class TradeDecisionRules(unittest.TestCase):
    def test_two_players_do_not_erase_unreplaced_core_cost(self):
        self.assertEqual(trade_verdict(True, False, 0.3, 0.2, "Win now"), "Decline this trade")

    def test_injury_patch_can_hide_recovery_loss(self):
        self.assertEqual(trade_verdict(False, True, 0.2, -0.3, "Win now"), "Decline this trade")

    def test_improvement_can_receive_actionable_verdict(self):
        self.assertEqual(trade_verdict(False, True, 0.3, 0.2, "Win now"), "Worth pursuing")

    def test_neutral_package_needs_revision(self):
        self.assertEqual(trade_verdict(False, True, 0.02, 0, "Win now"), "Revise the package")

    def test_missing_ratings_are_an_evidence_gap(self):
        self.assertEqual(
            trade_verdict(True, False, 0.2, 0.2, "Win now", True), "Needs more evidence"
        )


class OwnerImpactRules(unittest.TestCase):
    def test_real_position_upgrade_is_green(self):
        self.assertEqual(
            owner_goal_signal("Position upgrade", 0, 0, False, [0.5, 0.3])["signal"], "green"
        )

    def test_unchanged_position_is_red_without_claiming_harm(self):
        r = owner_goal_signal("Position upgrade", 0, 0, False, [0, 0])
        self.assertEqual(r["signal"], "red")
        self.assertEqual(r["label"], "No demonstrated progress")

    def test_worse_position_is_red(self):
        self.assertEqual(
            owner_goal_signal("Position upgrade", 0, 0, False, [-0.5, -0.3])["label"],
            "Works against the goal",
        )

    def test_split_tradeoff_is_amber(self):
        self.assertEqual(
            owner_goal_signal("Position upgrade", 0, 0, False, [0.8, -0.2])["signal"], "amber"
        )

    def test_current_help_and_future_cost_can_have_different_colors(self):
        self.assertEqual(owner_goal_signal("Playoffs", 0.3, 0.2, True)["signal"], "green")
        self.assertEqual(owner_goal_signal("Championship window", 0.3, 0.2, True)["signal"], "red")

    def test_controlled_core_addition_can_support_long_window(self):
        self.assertEqual(
            owner_goal_signal("Championship window", 0.2, 0.1, False, core_gain=True)["signal"],
            "green",
        )

    def test_unknown_popularity_chemistry_and_fan_response_are_not_invented(self):
        for category in ["Popularity", "Chemistry", "Fan interest"]:
            self.assertEqual(owner_goal_signal(category, 0.3, 0.2, False)["signal"], "amber")


from storage import current


@unittest.skipUnless(current(), "Local export unavailable")
class TradeReviewLive(unittest.TestCase):
    def test_trading_our_young_star_for_lesser_pieces_is_declined(self):
        # Picks players from whatever the save looks like now (Roman Anthony, the original
        # example, was traded to Toronto in Derek's save in July 2026).
        from department import department
        from frontoffice import evaluate
        from value import value_engine

        d = department()
        e = value_engine(d)
        ratings = d.ratings["players_value"]

        def rating(p, key):
            return float(ratings.get(p["id"], {}).get(key) or 0)

        core = [
            p
            for p in d.active()
            if p["kind"] == "bat" and p["age"] <= 28 and rating(p, "oa_rating") >= 7
        ]
        star = max(core, key=lambda p: e.player(p)["value"])
        others = [
            p
            for p in d.profiles
            if p["league_id"] == d.league
            and p["team_id"] not in (0, d.team)
            and p["kind"] == "bat"
            and not p["free_agent"]
            and 4 <= rating(p, "oa_rating") <= 5
        ]
        club = others[0]["team_id"]
        lesser = [p for p in others if p["team_id"] == club][:2]
        before = d.by_id[star["id"]].copy()
        r = evaluate(
            d,
            {"type": "Trade", "send": [star["id"]], "receive": [p["id"] for p in lesser]},
        )
        t = r["trade_review"]
        # The assistant GM's call leads; the analytics department still declines underneath.
        self.assertIn(r["call"]["call"], ["Don't", "Hang up"])
        self.assertTrue(r["recommendation"].startswith(r["call"]["call"]))
        self.assertEqual(t["verdict"], "Decline this trade")
        self.assertIn(f"Keep {star['name']}", t["lead"])
        self.assertEqual(len(t["comparisons"]), 2)
        self.assertEqual(d.by_id[star["id"]], before)  # reviewing never changes the player
        self.assertTrue(
            all(x.get("signal") in ["red", "green", "amber"] for x in t["owner_impact"])
        )


if __name__ == "__main__":
    unittest.main()
