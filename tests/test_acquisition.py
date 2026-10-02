import unittest
from acquisition import market_context


class MarketRealism(unittest.TestCase):
    def player(self, **kw):
        return dict(
            {
                "age": 24,
                "kind": "bat",
                "free_agent": False,
                "service_years": 2,
                "engine_percentile": 92,
                "rating_component": 6.75,
            },
            **kw
        )

    def test_langford_profile_is_premium_despite_low_payroll(self):
        p = self.player()
        p["salary"] = 780000
        a = market_context(
            p,
            {"oa_rating": 8, "pot_rating": 10},
            {
                "batting_ratings_talent_contact": 7,
                "batting_ratings_talent_gap": 10,
                "batting_ratings_talent_power": 9,
                "batting_ratings_talent_eye": 8,
                "batting_ratings_talent_strikeouts": 7,
            },
            {"fielding_rating_pos7": 8},
        )
        self.assertTrue(a["premium"])
        self.assertFalse(a["price_known"])
        self.assertEqual(a["tier"], "Premium trade target")
        self.assertIn("one-year", " ".join(a["reasons"]))

    def test_free_agent_does_not_have_invented_trade_package(self):
        a = market_context(self.player(free_agent=True), {"oa_rating": 8, "pot_rating": 10}, {}, {})
        self.assertFalse(a["premium"])
        self.assertEqual(a["tier"], "Free-agent inquiry")
        self.assertFalse(a["price_known"])

    def test_ordinary_veteran_is_an_inquiry_not_confirmed_available(self):
        a = market_context(
            self.player(age=33, engine_percentile=55, rating_component=5.5, service_years=8),
            {"oa_rating": 5, "pot_rating": 5},
            {},
            {},
        )
        self.assertFalse(a["premium"])
        self.assertEqual(a["availability"], "Trade availability unconfirmed")

    def test_elite_upside_detected_even_without_overall_potential(self):
        a = market_context(
            self.player(engine_percentile=50, rating_component=5),
            {},
            {
                "batting_ratings_talent_contact": 8,
                "batting_ratings_talent_power": 9,
                "batting_ratings_talent_eye": 8,
            },
            {},
        )
        self.assertTrue(a["premium"])

    def test_strong_controlled_veteran_is_not_a_salary_bargain(self):
        a = market_context(
            self.player(age=32, service_years=4, engine_percentile=70, rating_component=7),
            {"oa_rating": 7, "pot_rating": 7},
            {},
            {},
        )
        self.assertTrue(a["premium"])

    def test_service_threshold_uses_save_rule(self):
        self.assertFalse(market_context(self.player(service_years=4), {}, {}, {}, 3)["controlled"])


if __name__ == "__main__":
    unittest.main()

from storage import current
from department import department
from frontoffice import Office


@unittest.skipUnless(current(), "Local exports unavailable")
class LiveAcquisition(unittest.TestCase):
    def test_langford_not_recommended_as_cheap_help_or_edge(self):
        r = Office(department()).acquisitions()
        pid = 40026
        self.assertNotIn(pid, [p["id"] for p in r["players"]])
        self.assertNotIn(pid, [x["player"]["id"] for x in r["edges"]])
        self.assertIn(pid, [p["id"] for p in r["premium"]])
        self.assertIn(pid, [p["id"] for p in r["all_players"]])
        self.assertTrue(
            all(
                p["acquisition"]["need"]
                and p["acquisition"]["upgrade"]
                and not p["acquisition"]["premium"]
                for p in r["players"]
            )
        )
