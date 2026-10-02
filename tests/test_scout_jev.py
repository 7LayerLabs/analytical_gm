import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import current
import jev_reads


class JevShapes(unittest.TestCase):
    def test_question_sets_use_the_three_primitives_correctly(self):
        for qs in (
            jev_reads.prospect_questions("pit"),
            jev_reads.prospect_questions("bat"),
            jev_reads.trade_questions(),
            jev_reads.fit_questions(),
        ):
            for q in qs.values():
                self.assertIn(q["type"], ["score", "noul", "choice"])
                if q["type"] == "score":
                    self.assertTrue(2 <= len(q["criteria"]) <= 10)
                if q["type"] == "choice":
                    self.assertIsInstance(q["criteria"], dict)

    def test_free_questions_pick_among_players_or_answer_yes_no(self):
        pick = jev_reads.free_question("Who is the better fit at 2B?", ["A", "B"])["answer"]
        self.assertEqual(pick["type"], "choice")
        self.assertIn("none of them", pick["criteria"])
        yes_no = jev_reads.free_question("Should we call him up?", ["A"])["answer"]
        self.assertEqual(yes_no["type"], "noul")
        with self.assertRaises(ValueError):
            jev_reads.free_question("", ["A"])

    def test_validation_rejects_bad_answers(self):
        qs = jev_reads.trade_questions()
        good = {
            "answers": {
                "verdict": {
                    "type": "choice",
                    "choice": "decline",
                    "confidence": 0.8,
                    "probabilities": {"take": 0.1, "counter": 0.1, "decline": 0.8},
                },
                "fills_need": {"type": "noul", "noul": 0.3},
                "regret": {"type": "score", "score": 2.4, "confidence": 0.7, "probabilities": {}},
            }
        }
        jev_reads.validate(good, qs)
        bad = {
            "answers": {
                **good["answers"],
                "verdict": {**good["answers"]["verdict"], "choice": "maybe"},
            }
        }
        with self.assertRaises(ValueError):
            jev_reads.validate(bad, qs)
        off_scale = {
            "answers": {
                **good["answers"],
                "regret": {"type": "score", "score": 9, "confidence": 0.5},
            }
        }
        with self.assertRaises(ValueError):
            jev_reads.validate(off_scale, qs)

    def test_trade_read_says_whether_jev_agrees(self):
        qs = jev_reads.trade_questions()
        response = {
            "answers": {
                "verdict": {
                    "type": "choice",
                    "choice": "decline",
                    "confidence": 0.8,
                    "probabilities": {"take": 0.1, "counter": 0.1, "decline": 0.8},
                },
                "fills_need": {"type": "noul", "noul": 0.3},
                "regret": {"type": "score", "score": 2.6, "confidence": 0.7},
            }
        }
        agree = jev_reads.describe("trade", response, qs, {"call": "Hang up"})[0]
        self.assertTrue(agree["agrees"])
        disagree = jev_reads.describe("trade", response, qs, {"call": "Do it"})[0]
        self.assertFalse(disagree["agrees"])
        self.assertIn("Disagrees", disagree["detail"])


@unittest.skipUnless(current(), "Requires a local OOTP export")
class LiveScout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from department import department
        from frontoffice import Office
        from scout import Scout

        cls.d = department()
        cls.s = Scout(Office(cls.d))

    def test_reports_cover_ours_theirs_and_free_agents(self):
        ours = next(p for p in self.d.active() if p["kind"] == "bat")
        theirs = next(
            p
            for p in self.d.profiles
            if p["league_id"] == self.d.league
            and p["team_id"] != self.d.team
            and p["kind"] == "bat"
            and not p["free_agent"]
        )
        fa = next(p for p in self.d.profiles if p["free_agent"] and not p["draft_eligible"])
        reports = self.s.compare([ours["id"], theirs["id"], fa["id"]])["reports"]
        self.assertEqual(reports[0]["fit"]["role"], "Ours")
        self.assertEqual(reports[2]["money"]["label"], "Free agent")
        for r in reports:
            self.assertTrue(r["verdict"])
            self.assertTrue(r["summary"])
            self.assertIn(
                r["fenway"]["verdict"],
                ["plays up", "plays down", "neutral", "mostly plays up", "mostly plays down"],
            )
            self.assertTrue(r["tools"])
