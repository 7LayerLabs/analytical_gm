import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import current
from value import aging_curve, development_curve, dollars, fit_line, progress


class ValueMath(unittest.TestCase):
    def test_fit_line_recovers_a_line(self):
        a, b = fit_line([(x, 2 + 0.5 * x) for x in range(40, 81)])
        self.assertAlmostEqual(a, 2)
        self.assertAlmostEqual(b, 0.5)

    def test_development_curve_never_drops_and_needs_samples(self):
        rows = [(20, 60, 100)] * 30 + [(21, 50, 100)] * 30 + [(22, 90, 100)] * 5
        curve = development_curve(rows)
        self.assertAlmostEqual(curve[20], 0.6)
        self.assertAlmostEqual(curve[21], 0.6)  # a dip is ignored
        self.assertAlmostEqual(curve[22], 0.6)  # five players is not enough evidence
        self.assertEqual(sorted(curve.values()), list(curve.values()))

    def test_progress_closes_the_gap_by_26(self):
        curve = {age: 0.5 + 0.05 * (age - 15) for age in range(15, 26)}
        self.assertEqual(progress(curve, 22, 22), 0.0)
        self.assertEqual(progress(curve, 22, 26), 1.0)
        self.assertGreater(progress(curve, 22, 24), 0)
        self.assertLess(progress(curve, 22, 24), 1)
        self.assertEqual(progress(curve, 30, 33), 1.0)  # fully developed players don't grow

    def test_aging_curve_weights_and_smooths(self):
        rows = [(30, -1.0, 100)] * 30 + [(31, 0.0, 100)] * 30 + [(32, -0.5, 100)] * 30
        curve = aging_curve(rows)
        self.assertAlmostEqual(curve[31], -0.5)
        self.assertEqual(aging_curve([(30, -1.0, 100)] * 5), {})

    def test_dollars_reads_like_a_person(self):
        self.assertEqual(dollars(177_400_000), "$177M")
        self.assertEqual(dollars(5_200_000), "$5.2M")
        self.assertEqual(dollars(740_000), "$740K")
        self.assertEqual(dollars(-5_000_000), "-$5.0M")


@unittest.skipUnless(current(), "Requires a local OOTP export")
class LiveValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from department import department
        from value import value_engine

        cls.d = department()
        cls.e = value_engine(cls.d)

    def value(self, p):
        return self.e.player(p)

    def test_calibration_is_baseball_sane(self):
        self.assertGreater(self.e.dollars_per_war, 3_000_000)
        self.assertLess(self.e.dollars_per_war, 15_000_000)
        for role, (a, b) in self.e.lines.items():
            self.assertGreater(b, 0, role)  # better ratings mean more wins
        self.assertGreater(self.e.war_rate("bat", 80), self.e.war_rate("bat", 50))

    def test_young_cheap_stars_beat_expensive_veterans(self):
        own = [self.value(p) for p in self.d.own() if not p["free_agent"]]
        best, worst = max(own, key=lambda v: v["value"]), min(own, key=lambda v: v["value"])
        self.assertGreater(best["value"], 50_000_000)
        self.assertLess(worst["value"], 0)
        self.assertIn("more than he's worth", worst["summary"])

    def test_seasons_respect_control_and_horizon(self):
        for p in self.d.own()[:80]:
            v = self.value(p)
            if v["free_agent"] or not v["seasons"]:
                continue
            years = [s["year"] for s in v["seasons"]]
            self.assertEqual(years, list(range(self.d.year, self.d.year + len(years))))
            self.assertLessEqual(len(years), 12)
            self.assertTrue(all(s["war"] >= 0 for s in v["seasons"]))
            self.assertLessEqual(v["seasons"][0]["war"], v["seasons"][0]["full_season_war"])

    def test_free_agents_get_a_market_price_not_a_surplus(self):
        fa = next(p for p in self.d.profiles if p["free_agent"] and not p["draft_eligible"])
        v = self.value(fa)
        self.assertTrue(v["free_agent"])
        self.assertIn("asking_value", v)
        self.assertNotIn("value", v)

    def test_prospects_carry_development_risk(self):
        minors = [
            p
            for p in self.d.own()
            if self.e.level(p) and self.e.level(p) > 1 and p["age"] < 24 and not p["free_agent"]
        ]
        v = self.value(minors[0])
        self.assertLess(v["chance_develops"], 1)
        self.assertEqual(v["risk"], "Prospect")
