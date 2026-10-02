import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import current


@unittest.skipUnless(current(), "Requires a local OOTP export")
class LiveOffers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from department import department
        from frontoffice import Office
        from value import value_engine

        cls.d = department()
        cls.o = Office(cls.d)
        e = value_engine(cls.d)
        own = [p for p in cls.d.own() if not p["free_agent"]]
        ranked = sorted(own, key=lambda p: e.player(p)["value"])
        cls.star, cls.dead_money = ranked[-1], ranked[0]
        others = [
            p
            for p in cls.d.profiles
            if p["league_id"] == cls.d.league and p["team_id"] != cls.d.team and not p["free_agent"]
        ]
        priced = sorted(((e.player(p)["value"], p) for p in others), key=lambda x: x[0])
        cls.modest = [p for v, p in priced if 5e6 <= v <= 30e6][:3]
        cls.minor_leaguer = next(
            p
            for p in cls.d.profiles
            if p["organization_id"]
            and p["organization_id"] != cls.d.team
            and p["team_id"] != p["organization_id"]
            and e.player(p).get("value", 0) > 5e6
        )

    def compare(self, block, offers, mode="Win now"):
        from offers import compare_offers

        return compare_offers(self.o, [block["id"]], [{"receive": [p["id"]]} for p in offers], mode)

    def test_offers_are_ranked_by_our_edge(self):
        r = self.compare(self.dead_money, self.modest)
        edges = [o["call"]["edge"] for o in r["offers"]]
        self.assertEqual(edges, sorted(edges, reverse=True))
        self.assertIn(r["verdict"]["call"], ["Do it", "Do it if..."])
        self.assertTrue(r["verdict"]["reasons"])

    def test_keep_the_star_when_every_offer_is_light(self):
        r = self.compare(self.star, self.modest)
        self.assertEqual(r["verdict"]["call"], "Don't")
        self.assertTrue(r["verdict"]["headline"].startswith(f"Keep {self.star['name']}"))

    def test_offers_name_the_big_league_club_not_the_affiliate(self):
        r = self.compare(self.dead_money, [self.minor_leaguer, self.modest[0]])
        club = self.d.team_name(self.minor_leaguer["organization_id"])
        self.assertIn(f"{club} offer", [o["label"] for o in r["offers"]])

    def test_needs_two_to_four_offers(self):
        with self.assertRaisesRegex(ValueError, "two and four"):
            self.compare(self.dead_money, self.modest[:1])

    def test_rebuilding_never_argues_for_wins_this_season(self):
        r = self.compare(self.dead_money, self.modest, mode="Rebuild")
        self.assertFalse(any("better for this season" in x for x in r["verdict"]["reasons"]))
