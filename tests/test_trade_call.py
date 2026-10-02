import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import current
from trade_call import decide, roster_lines


class CallScale(unittest.TestCase):
    def test_clear_wins_are_do_it(self):
        self.assertEqual(decide(60e6, 100e6), ("Do it", "strong"))
        self.assertEqual(decide(20e6, 100e6), ("Do it", "lean"))
        self.assertEqual(decide(1e6, 100e6), ("Do it", "lean"))

    def test_close_losses_need_something_added(self):
        self.assertEqual(decide(-10e6, 100e6)[0], "Do it if...")

    def test_real_losses_are_dont_and_absurd_ones_hang_up(self):
        self.assertEqual(decide(-25e6, 100e6), ("Don't", "lean"))
        self.assertEqual(decide(-45e6, 100e6), ("Don't", "strong"))
        self.assertEqual(decide(-126e6, 151e6), ("Hang up", "strong"))
        # A big ratio on a small deal is still just "Don't"
        self.assertEqual(decide(-27e6, 52e6)[0], "Don't")

    def test_small_deals_are_not_judged_on_pennies(self):
        self.assertEqual(decide(-1e6, 2e6)[0], "Do it if...")


class RosterLines(unittest.TestCase):
    def card(self, name):
        return {"name": name}

    def test_says_who_is_in_and_out_not_every_shuffle(self):
        review = {
            "comparisons": [
                {
                    "hand": "vsr",
                    "changes": [
                        {
                            "role": "CF",
                            "before": self.card("Anthony"),
                            "after": self.card("Rafaela"),
                        },
                        {
                            "role": "SS",
                            "before": self.card("Rafaela"),
                            "after": self.card("Sogard"),
                        },
                        {
                            "role": "RP 1",
                            "before": self.card("Chapman"),
                            "after": self.card("Smith"),
                        },
                        {
                            "role": "RP 2",
                            "before": self.card("Whitlock"),
                            "after": self.card("Chapman"),
                        },
                        {"role": "RP 3", "before": None, "after": self.card("Whitlock")},
                    ],
                }
            ]
        }
        lines = roster_lines(review)
        self.assertEqual(lines[0], "Lineup vs righties: Anthony out, Sogard in (Rafaela to CF).")
        self.assertEqual(lines[1], "Bullpen: Smith in.")
        self.assertEqual(roster_lines(None), [])


@unittest.skipUnless(current(), "Requires a local OOTP export")
class LiveCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from department import department
        from frontoffice import Office
        from value import value_engine

        cls.d = department()
        cls.o = Office(cls.d)
        cls.e = value_engine(cls.d)
        own = [p for p in cls.d.own() if not p["free_agent"]]
        values = sorted(((cls.e.player(p)["value"], p) for p in own), key=lambda x: x[0])
        cls.best, cls.worst = values[-1][1], values[0][1]
        others = [
            p
            for p in cls.d.profiles
            if p["league_id"] == cls.d.league and p["team_id"] != cls.d.team and not p["free_agent"]
        ]
        priced = sorted(((cls.e.player(p)["value"], p) for p in others), key=lambda x: x[0])
        cls.modest = next(p for v, p in priced if 5e6 <= v <= 30e6)

    def call(self, send, receive):
        from trade_call import trade_call

        return trade_call(self.o, [p["id"] for p in send], [p["id"] for p in receive], "Win now")

    def test_giving_our_best_player_for_a_modest_one_is_hang_up(self):
        c = self.call([self.best], [self.modest])
        self.assertEqual(c["call"], "Hang up")
        self.assertTrue(c["cons"])
        self.assertIn("make it even", c["make_it_work"])

    def test_dumping_our_worst_contract_for_a_useful_player_is_good_value(self):
        c = self.call([self.worst], [self.modest])
        # Good value either way; a contender is told to replace him first if he leaves a hole.
        self.assertGreater(c["edge"], 0)
        self.assertIn(c["call"], ["Do it", "Do it if..."])
        if c["call"] == "Do it if...":
            self.assertIn("replace", c["make_it_work"])
        self.assertTrue(any(p.startswith("Sheds") for p in c["pros"]))

    def test_zero_value_depth_is_never_a_reason_to_trade(self):
        depth = next(
            p
            for p in self.d.own()
            if p["team_id"] != self.d.team
            and not p["secondary"]
            and self.e.player(p).get("value", 0) == 0
            and not p["free_agent"]
        )
        c = self.call([depth], [self.modest])
        self.assertFalse(any(depth["name"] in p for p in c["pros"]))
        self.assertTrue(any(f"We also give up {depth['name']}" in x for x in c["cons"]))

    def test_every_call_names_the_players_and_dollars(self):
        c = self.call([self.best], [self.modest])
        self.assertEqual(c["give_players"][0]["name"], self.best["name"])
        self.assertIn("$", c["headline"])
