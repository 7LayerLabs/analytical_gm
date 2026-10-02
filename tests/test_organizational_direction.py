import unittest
from organizational_direction import direction_category


class OrganizationalRules(unittest.TestCase):
    def category(self, **kw):
        args = dict(
            age=26,
            current=8,
            potential=9,
            active=True,
            controlled=True,
            now="Win now",
            next_year="Win now",
            surplus=False,
            expiring=False,
            locked=False,
        )
        args.update(kw)
        return direction_category(**args)

    def test_young_controlled_impact_is_foundation_even_with_overlap(self):
        self.assertEqual(self.category(surplus=True), "Build-around core")

    def test_minor_league_potential_is_separate_from_ready_now(self):
        self.assertEqual(self.category(age=21, current=4, active=False), "Development cornerstone")

    def test_age_alone_does_not_trigger_sale(self):
        self.assertEqual(self.category(age=35), "Current-window pillar")

    def test_contending_next_year_keeps_impact_pillar(self):
        self.assertEqual(self.category(age=32, now="Selective sell"), "Current-window pillar")

    def test_surplus_can_be_explored_without_rebuilding(self):
        self.assertEqual(
            self.category(age=32, current=5, potential=5, surplus=True), "Explore a surplus trade"
        )

    def test_expiring_piece_changes_with_window(self):
        self.assertEqual(
            self.category(age=32, current=5, potential=5, controlled=False, expiring=True),
            "Keep evaluating",
        )
        self.assertEqual(
            self.category(
                age=32, current=5, potential=5, controlled=False, expiring=True, next_year="Rebuild"
            ),
            "Explore before control expires",
        )

    def test_trade_lock_has_priority_over_sale(self):
        self.assertEqual(
            self.category(age=32, current=5, surplus=True, locked=True), "Protected by GM"
        )


from storage import current
from department import department
from frontoffice import Office
from organizational_direction import organizational_direction


@unittest.skipUnless(current(), "Local export unavailable")
class OrganizationalLive(unittest.TestCase):
    def test_core_and_sale_are_disjoint_and_crochet_is_preserved(self):
        r = organizational_direction(Office(department()))
        core = {x["player"]["id"] for x in r["core"]}
        trade = {x["player"]["id"] for x in r["trade"]}
        self.assertFalse(core & trade)
        self.assertIn(37550, core)
        self.assertNotIn(37550, trade)
        self.assertTrue(all(x["facts"] and x["condition"] for x in r["core"] + r["trade"]))
        self.assertTrue(
            all(
                x["player"]["team_id"] == 4
                for x in r["trade"]
                if x["category"] == "Explore a surplus trade"
            )
        )
        self.assertNotIn(43008, trade)
        self.assertNotIn(40739, trade)


if __name__ == "__main__":
    unittest.main()
