import unittest
from roster_moves import option_review


class AssignmentRules(unittest.TestCase):
    def test_active_restriction_is_not_a_routine_option(self):
        self.assertEqual(option_review({"must_be_active": 1, "options_used": 0})[0], "Restricted")

    def test_veteran_rights(self):
        self.assertEqual(
            option_review({"mlb_service_years": 5, "options_used": 0})[0], "Consent review"
        )

    def test_exhausted_options_are_not_simple_demotions(self):
        self.assertEqual(option_review({"options_used": 3})[0], "Waiver / option review")

    def test_missing_options_are_not_assumed_available(self):
        self.assertEqual(option_review({})[0], "Unknown options")

    def test_used_current_year_is_distinct(self):
        self.assertEqual(
            option_review({"options_used": 3, "options_used_this_year": 1})[0],
            "Option already used this year",
        )

    def test_available_route_remains_conditional(self):
        self.assertIn("Confirm", option_review({"options_used": 1})[1])


from storage import current


@unittest.skipUnless(current(), "Local export unavailable")
class PairedMovesLive(unittest.TestCase):
    def test_unique_outgoing_players_and_backup_catcher(self):
        from department import department
        from frontoffice import Office

        d = department()
        o = Office(d)
        r = o.roster(internal=True)
        selected = (
            {x["player"]["id"] for x in r["lineup"]}
            | {x["player"]["id"] for x in r["rotation"] if x["player"]}
            | {x["player"]["id"] for x in r["bullpen"]}
            | {x["id"] for x in r["bench"]}
        )
        down = [m["down"]["player"]["id"] for m in r["moves"]["moves"] if m["down"]]
        self.assertEqual(len(down), len(set(down)))
        self.assertFalse(set(down) & selected)
        self.assertGreaterEqual(
            sum(
                1
                for pid in selected
                if d.by_id[pid]["kind"] == "bat"
                and float(
                    d.ratings["players_fielding"].get(pid, {}).get("fielding_rating_pos2") or 0
                )
                >= 4
            ),
            2,
        )
        for m in r["moves"]["moves"]:
            if m["down"] and m["down"]["route"] in [
                "Restricted",
                "Consent review",
                "Waiver / option review",
                "Unknown options",
            ]:
                self.assertTrue(m["verdict"].startswith("Do not"))


if __name__ == "__main__":
    unittest.main()
