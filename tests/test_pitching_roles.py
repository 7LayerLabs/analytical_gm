import unittest
from pitching_roles import pitch_limit, bullpen_assignments


def arm(pid, quality=6, stamina=3, vsr=6, vsl=6, qualified=False):
    return {
        "id": pid,
        "quality": quality,
        "stamina": stamina,
        "vsr": vsr,
        "vsl": vsl,
        "starter_qualified": qualified,
        "evidence_ip": 50,
        "unavailable": False,
        "notes": [],
    }


class PitchingRoles(unittest.TestCase):
    def test_closer_and_setup_are_unique(self):
        r = bullpen_assignments([arm(1, 7), arm(2, 6), arm(3, 4.9)])
        self.assertEqual(
            [(p["role"], p["usage"]) for p in r],
            [
                ("Closer", "9th or later"),
                ("Setup", "8th or later"),
                ("Middle Relief", "Normal Usage"),
            ],
        )

    def test_seventh_inning_bridge_and_stronger_middle_usage(self):
        r = bullpen_assignments([arm(1, 7), arm(2, 6.5), arm(3, 5.6), arm(4, 5.2)])
        self.assertEqual((r[2]["role"], r[2]["usage"]), ("Setup", "7th or later"))
        self.assertEqual(r[3]["usage"], "Use more often")

    def test_long_relief_has_emergency_starting_coverage(self):
        r = bullpen_assignments([arm(1, 7), arm(2, 6), arm(3, 5, 7, qualified=True)])
        self.assertEqual(r[2]["role"], "Long Relief")
        self.assertEqual(r[2]["secondary_role"], "Emergency SP")

    def test_platoon_specialist_requires_actual_rating_gap(self):
        r = bullpen_assignments([arm(1, 7), arm(2, 6), arm(3, 5, vsr=4, vsl=6)])
        self.assertEqual(r[2]["role"], "Specialist")
        self.assertIn("left-handed", " ".join(r[2]["notes"]))

    def test_weak_middle_arm_avoids_high_leverage(self):
        r = bullpen_assignments([arm(1, 7), arm(2, 6), arm(3, 4)])
        self.assertEqual(r[2]["usage"], "Avoid high leverage")

    def test_analytics_stopper_requires_stamina_and_both_splits(self):
        r = bullpen_assignments([arm(1, 7, 6), arm(2, 6)], "Analytics-led")
        self.assertEqual(r[0]["role"], "Stopper")
        self.assertIsNone(r[0]["usage"])
        self.assertEqual(r[1]["secondary_role"], "Closer")
        r = bullpen_assignments([arm(1, 7, 6, vsr=4), arm(2, 6)], "Analytics-led")
        self.assertEqual(r[0]["role"], "Closer")

    def test_unavailable_arm_never_gets_closer_job(self):
        p = arm(1, 9)
        p["unavailable"] = True
        r = bullpen_assignments([p, arm(2, 6)])
        self.assertEqual(r[0]["role"], "None specified")
        self.assertEqual(r[1]["role"], "Closer")

    def test_missing_ratings_do_not_become_a_real_role(self):
        self.assertEqual(bullpen_assignments([arm(1, None)])[0]["role"], "None specified")

    def test_starter_limit_uses_established_workload(self):
        h = {"year": 2025, "g": 32, "gs": 32, "pi": 3151, "outs": 616}
        self.assertEqual(pitch_limit(5, h)[0], 95)
        self.assertLessEqual(pitch_limit(10, h)[0], 105)

    def test_unknown_workload_and_small_prior_innings_are_conservative(self):
        self.assertEqual(pitch_limit(8)[0], 85)
        self.assertLessEqual(pitch_limit(8, {"g": 10, "gs": 10, "pi": 950, "outs": 150})[0], 85)

    def test_missing_stamina_or_unavailability_has_no_usable_cap(self):
        self.assertIsNone(pitch_limit(0)[0])
        self.assertIsNone(pitch_limit(8, unavailable=True)[0])

    def test_relief_appearances_are_not_treated_as_start_pitch_counts(self):
        cap, notes = pitch_limit(8, {"year": 2025, "g": 40, "gs": 5, "pi": 600, "outs": 180})
        self.assertEqual(cap, 85)
        self.assertFalse(any("pitches per appearance" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
