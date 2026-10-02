import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import current
from moves import league_rank


class Wording(unittest.TestCase):
    def test_league_rank_reads_like_a_scout(self):
        self.assertEqual(
            league_rank({"quality_percentile": 96.8, "qualified": True, "league": "IL"}),
            "top 3% of the IL",
        )
        self.assertEqual(
            league_rank({"quality_percentile": 85, "qualified": True, "league": "IL"}),
            "better than 85% of the IL",
        )
        self.assertEqual(
            league_rank({"quality_percentile": 50, "qualified": True, "league": "EL"}),
            "about average in the EL",
        )
        self.assertEqual(
            league_rank({"quality_percentile": 7, "qualified": True, "league": "MLB"}),
            "bottom 7% of the MLB",
        )
        self.assertEqual(
            league_rank({"quality_percentile": 99, "qualified": False, "league": "IL"}), ""
        )


@unittest.skipUnless(current(), "Requires a local OOTP export")
class LiveMoves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from department import department
        from frontoffice import Office
        from moves import Moves

        cls.d = department()
        cls.m = Moves(Office(cls.d))
        cls.result = cls.m.all()

    def test_every_suggestion_is_a_chain_with_comparisons(self):
        for move in self.result["moves"]:
            self.assertIn(move["call"], ["Do it", "Worth a look", "Be ready"])
            self.assertTrue(move["chain"], move["title"])
            self.assertTrue(move["comps"], move["title"])
            for c in move["comps"]:
                self.assertTrue(c["line"])
                self.assertIn("wins", c)

    def test_day_to_day_players_stay_on_the_roster(self):
        playing = {x["player"]["id"] for x in self.m.roster["rotation"] if x["player"]}
        playing |= {x["player"]["id"] for x in self.m.roster["lineup"] if x["player"]}
        for p in self.d.own():
            if p["day_to_day"] and p["team_id"] == self.d.team and p["active"]:
                self.assertFalse(p["injured"], p["name"])

    def test_nobody_is_promised_twice(self):
        called_up = [
            m["comps"][0]["id"]
            for m in self.result["moves"]
            if m["call"] in ("Do it", "Worth a look")
        ]
        self.assertEqual(len(called_up), len(set(called_up)))

    def test_rankings_match_the_readiness_desk(self):
        from readiness import ReadinessDesk

        desk = ReadinessDesk(self.d, self.d.team)
        checked = 0
        for p in self.d.own():
            mine = [r for r in self.m.this_year.get((p["kind"], p["id"]), []) if r["qualified"]]
            if not mine:
                continue
            rows, _ = desk.statistics(p)
            theirs = {
                r["league_id"]: r["quality_percentile"] for r in rows if r["year"] == self.d.year
            }
            for r in mine:
                self.assertAlmostEqual(r["quality_percentile"], theirs[r["league_id"]], places=1)
            checked += 1
            if checked >= 5:
                break
        self.assertGreater(checked, 0)
