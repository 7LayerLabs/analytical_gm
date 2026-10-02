import unittest, tempfile
from pathlib import Path
from unittest.mock import patch
from frontoffice import save, office_state
from playstyle import generate_style
from frontoffice import SKILLS
from readiness import readiness_verdict, ReadinessDesk, team_view
from department import department
from storage import current


class PlayingStyle(unittest.TestCase):
    def test_moneyball_values_onbase_without_power_requirement(self):
        r = generate_style(["moneyball"], SKILLS)
        self.assertEqual(r["skills"]["On-base ability"], "Essential")
        self.assertEqual(r["skills"]["Power"], "Optional")

    def test_primary_controls_blend(self):
        a = generate_style(["traditional", "moneyball"], SKILLS)
        b = generate_style(["moneyball", "traditional"], SKILLS)
        self.assertEqual(a["philosophy"], "Blended")
        self.assertEqual(a["skills"]["Speed"], "Essential")
        self.assertEqual(b["skills"]["Speed"], "Preferred")

    def test_neutral_defaults_and_validation(self):
        self.assertTrue(
            all(v == "Preferred" for v in generate_style([], SKILLS)["skills"].values())
        )
        for ids in [["unknown"], ["farm", "farm"]]:
            with self.assertRaises(ValueError):
                generate_style(ids, SKILLS)


class ReadinessRules(unittest.TestCase):
    def verdict(self, **changes):
        a = dict(
            injured=False,
            active=False,
            current_percentile=70,
            qualified=True,
            stats={"recent": True, "qualified": True, "level": 2, "quality_percentile": 70},
        )
        a.update(changes)
        return readiness_verdict(**a)[0]

    def test_upper_level_evidence_can_support_trial(self):
        self.assertEqual(self.verdict(), "Ready for an MLB trial")

    def test_injury_precedes_rating(self):
        self.assertTrue(self.verdict(injured=True).startswith("Wait"))

    def test_low_current_tools_do_not_become_ready(self):
        self.assertEqual(self.verdict(current_percentile=10), "Keep developing")

    def test_small_sample_cannot_prove_readiness(self):
        self.assertTrue(self.verdict(stats=None).startswith("Borderline"))

    def test_low_level_stats_cannot_prove_readiness(self):
        self.assertTrue(
            self.verdict(
                stats={"recent": True, "qualified": True, "level": 4, "quality_percentile": 99}
            ).startswith("Wait")
        )

    def test_missing_ratings_are_not_filled_by_upside(self):
        self.assertEqual(self.verdict(current_percentile=None), "Needs more evidence")

    def test_weak_stats_require_explanation(self):
        self.assertTrue(
            self.verdict(
                stats={"recent": True, "qualified": True, "level": 2, "quality_percentile": 20}
            ).startswith("Borderline")
        )


@unittest.skipUnless(current(), "Local exports unavailable")
class ReadinessLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = department()

    def test_early_reviews_real_stats_and_rotation(self):
        r = ReadinessDesk(self.d).review(40739)
        self.assertEqual(r["role"], "SP")
        self.assertTrue(r["stats"])
        self.assertTrue(r["incumbents"])
        self.assertTrue(all(s["league_id"] for s in r["stats"]))
        self.assertIn("potential", r)

    def test_foreign_organization_keeps_own_roster_context(self):
        desk = ReadinessDesk(self.d, 1)
        p = desk.listing()["players"][0]
        r = desk.review(p["id"])
        self.assertEqual(r["organization_id"], 1)
        self.assertEqual(self.d.team, 4)
        self.assertTrue(all(i["player"]["team_id"] == 1 for i in r["incumbents"]))

    def test_custom_style_survives_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "frontoffice.state_path", return_value=Path(tmp) / "office.json"
        ):
            b = office_state(self.d)["blueprint"]
            b.update(
                identities=["moneyball"],
                playing_notes="My custom approach",
                style_overrides=["playing_notes", "skill-Speed"],
                reason="Test custom draft",
            )
            b["skills"]["Speed"] = "Essential"
            save(self.d, {"action": "blueprint", "blueprint": b})
            loaded = office_state(self.d)["blueprint"]
            self.assertEqual(loaded["playing_notes"], "My custom approach")
            self.assertEqual(loaded["skills"]["Speed"], "Essential")
            self.assertEqual(loaded["style_source"], ["moneyball"])

    def test_invalid_role_is_clean_validation(self):
        with self.assertRaises(ValueError):
            ReadinessDesk(self.d).review(40739, "LF")

    def test_all_clubs_have_organizational_profiles(self):
        r = ReadinessDesk(self.d).listing(all_teams=True, limit=50)
        self.assertEqual(len(r["clubs"]), 30)
        self.assertGreater(r["total"], 3000)


if __name__ == "__main__":
    unittest.main()
