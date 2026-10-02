import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import current


@unittest.skipUnless(current(), "Requires a local OOTP export")
class LivePlayerCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from department import department
        from frontoffice import Office
        from value import value_engine

        cls.d = department()
        cls.o = Office(cls.d)
        cls.e = value_engine(cls.d)
        free = [p for p in cls.d.profiles if p["free_agent"] and not p["draft_eligible"]]
        cls.best_fa = max(free, key=cls.e.current_rate)
        own = [p for p in cls.d.own() if not p["free_agent"]]
        values = {p["id"]: cls.e.player(p) for p in own}
        cls.locked_up = next(
            p for p in own if (values[p["id"]].get("control_through") or 0) >= cls.d.year + 6
        )
        cls.near_fa = next(
            p
            for p in own
            if p["active"]
            and p["age"] < 30
            and cls.d.year + 1 <= (values[p["id"]].get("control_through") or 0) <= cls.d.year + 4
            and values[p["id"]]["peak_war"] >= 1.5
        )

    def test_free_agent_with_no_offer_gets_a_price(self):
        from player_calls import signing_call

        c = signing_call(self.o, self.best_fa, 0, 0, "Win now")
        self.assertIn(c["call"], ["Do it if...", "Don't"])
        if c["call"] == "Do it if...":
            self.assertIn("Sign him at up to $", c["headline"])
            self.assertEqual(c["ledger"][0]["label"], "Fair price")

    def test_a_huge_overpay_is_refused(self):
        from player_calls import signing_call

        c = signing_call(self.o, self.best_fa, 60_000_000, 5, "Win now")
        self.assertIn(c["call"], ["Don't", "Hang up"])
        self.assertIn("Offer no more than", c["make_it_work"])

    def test_signing_someone_under_contract_is_a_trade(self):
        from player_calls import signing_call

        c = signing_call(self.o, self.locked_up, 0, 0, "Win now")
        self.assertEqual(c["call"], "Don't")
        self.assertIn("That's a trade", c["headline"])

    def test_extending_inside_existing_control_is_no_need(self):
        from player_calls import extension_call

        c = extension_call(self.o, self.locked_up, 10_000_000, 2, self.d.year + 1, "Win now")
        self.assertEqual(c["call"], "Don't")
        self.assertIn("No need", c["headline"])

    def test_extension_recommends_a_price_below_break_even(self):
        from player_calls import extension_call

        c = extension_call(self.o, self.near_fa, 0, 0, None, "Win now")
        self.assertEqual(c["call"], "Do it if...")
        good, even = c["ledger"][0]["total"], c["ledger"][1]["total"]
        self.assertLess(good, even)
        self.assertTrue(any("free agency" in x for x in c["pros"]))

    def test_promotion_names_who_he_would_replace(self):
        from player_calls import promotion_call

        minors = [
            p
            for p in self.d.own()
            if (self.e.level(p) or 1) > 1 and not p["injured"] and not p["on_dl"]
        ]
        c = promotion_call(self.o, max(minors, key=self.e.current_rate), "Win now")
        self.assertIn(c["call"], ["Do it", "Do it if...", "Don't"])
        self.assertTrue(c["headline"])
