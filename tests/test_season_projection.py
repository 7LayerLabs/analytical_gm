import json, math, tempfile, unittest, copy
from pathlib import Path
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from season_projection import (
    base_runs,
    run_probability,
    park_counts,
    remaining_injury_games,
    SeasonModel,
    season_projection,
    VERSION,
)
from department import department
from storage import current
import season_projection as model


class SeasonMath(unittest.TestCase):
    def test_missing_history_does_not_invent_wins(self):
        with self.assertRaisesRegex(ValueError, "completed MLB season"):
            SeasonModel(SimpleNamespace(base_bat={}, base_pit={}))

    def test_each_matchup_has_exactly_one_expected_win(self):
        for a, b in [(4, 4), (6, 3), (1, 7)]:
            self.assertAlmostEqual(run_probability(a, b) + run_probability(b, a), 1)
        self.assertEqual(run_probability(4, 4), 0.5)

    def test_more_runs_and_fewer_allowed_improve_expectation(self):
        self.assertGreater(run_probability(5, 4), run_probability(4, 4))
        self.assertGreater(run_probability(4, 3), run_probability(4, 4))

    def test_park_change_applies_by_batting_side(self):
        counts = {"ab": 100, "h": 30, "d": 5, "t": 1, "hr": 4}
        park = {"hr_l": 0.8, "hr_r": 1.2, "avg": 1, "avg_l": 1, "avg_r": 1, "d": 1, "t": 1}
        self.assertAlmostEqual(park_counts(counts, park, "L")["hr"], 3.2)
        self.assertAlmostEqual(park_counts(counts, park, "R")["hr"], 4.8)

    def test_no_fake_absences_before_opening_day(self):
        start = date(2026, 3, 21)
        games = [start + timedelta(days=i) for i in [5, 6, 10, 11]]
        self.assertEqual(
            remaining_injury_games({"injured": True, "injury_days": 3}, games, start), 0
        )
        self.assertEqual(
            remaining_injury_games({"injured": True, "injury_days": 10}, games, start), 2
        )
        self.assertEqual(
            remaining_injury_games({"injured": True, "injury_days": 100}, games, start, True), 0
        )

    def test_opening_forecast_stays_fixed_across_new_exports(self):
        d = SimpleNamespace(
            sid="first", team=4, league=203, year=2026, manifest={"source_id": "test"}
        )
        first = {"snapshot": "first", "preseason": True, "club": {"wins": 89}}
        second = {"snapshot": "second", "preseason": False, "club": {"wins": 81}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            model, "DATA", Path(tmp)
        ), patch.object(
            model, "CACHE", {("first", VERSION, 4): first, ("second", VERSION, 4): second}
        ):
            initial = season_projection(d)
            self.assertEqual(initial["opening_forecast"]["club"]["wins"], 89)
            json.dumps(initial)
            d.sid = "second"
            r = season_projection(d)
            self.assertEqual(r["club"]["wins"], 81)
            self.assertEqual(r["opening_forecast"]["club"]["wins"], 89)
            self.assertEqual(r["delta_original"], -8)
            self.assertEqual(len(r["archive"]), 2)
            self.assertEqual(len(season_projection(d)["archive"]), 2)
            model.CACHE[(d.sid, VERSION, d.team)]["club"]["wins"] = 90
            self.assertEqual(
                season_projection(d)["archive"][-1]["wins"], 81
            )  # Immutable once archived.

    def test_midseason_capture_does_not_invent_preseason_baseline(self):
        d = SimpleNamespace(
            sid="late", team=4, league=203, year=2026, manifest={"source_id": "test"}
        )
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            model, "DATA", Path(tmp)
        ), patch.object(
            model,
            "CACHE",
            {("late", VERSION, 4): {"snapshot": "late", "preseason": False, "club": {"wins": 81}}},
        ):
            self.assertIsNone(season_projection(d)["opening_forecast"])
            self.assertEqual(list(Path(tmp).glob("preseason-*.json")), [])


@unittest.skipUnless(current(), "Requires a local OOTP export")
class LiveSeasonProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = SeasonModel(department())
        cls.r = cls.m.build()

    def test_only_scheduled_clubs_and_balanced_wins(self):
        self.assertEqual(len(self.r["league"]), 30)
        self.assertAlmostEqual(sum(c["expected_wins"] for c in self.r["league"]), len(self.m.games))
        self.assertEqual(sum(c["wins"] for c in self.r["league"]), len(self.m.games))
        self.assertEqual(len(self.r["division"]), 5)

    def test_workload_totals_do_not_duplicate_team_season(self):
        for club in [self.m.club(self.m.d.team), self.m.club(self.m.d.team, True)]:
            self.assertAlmostEqual(
                sum(s["workload"] for s in club["shares"] if s["kind"] == "bat"),
                club["games"] * self.m.pa_per_game,
            )
            self.assertAlmostEqual(
                sum(s["workload"] for s in club["shares"] if s["kind"] == "pit"), club["games"] * 9
            )

    def test_run_environment_calibration_matches_export(self):
        b = self.m.d.base_bat
        self.assertAlmostEqual(base_runs(b, self.m.multiplier), b["r"], places=5)

    def progressed(self, complete=False):
        m = copy.copy(self.m)
        m.games = copy.deepcopy(self.m.games)
        m.records = {tid: {"w": 0, "l": 0} for tid in m.clubs}
        # Synthetic progression starts from a clean schedule even when the live save is midseason.
        for g in m.games:
            g["played"] = 0
        played = m.games if complete else m.games[:35]
        for g in played:
            g["played"] = 1
            m.records[g["home_team"]]["w"] += 1
            m.records[g["away_team"]]["l"] += 1
        m.dates = {
            tid: [
                g["date"]
                for g in m.games
                if not g["played"] and tid in [g["home_team"], g["away_team"]]
            ]
            for tid in m.clubs
        }
        return m

    def test_midseason_finish_keeps_results_and_models_only_remaining_games(self):
        m = self.progressed()
        r = m.build()
        for club in r["league"]:
            self.assertAlmostEqual(
                club["expected_wins"],
                m.records[club["team_id"]]["w"] + club["remaining_expected_wins"],
            )
            self.assertEqual(club["played_games"] + club["remaining_games"], club["games"])
            self.assertGreaterEqual(club["range"]["low"], club["actual_wins"])
            self.assertLessEqual(
                club["range"]["high"], club["actual_wins"] + club["remaining_games"]
            )
        self.assertEqual(sum(c["wins"] for c in r["league"]), len(m.games))
        self.assertEqual(sum(c["remaining_expected_wins"] for c in r["league"]), len(m.games) - 35)

    def test_completed_season_is_actual_record_with_no_future_workload(self):
        m = self.progressed(True)
        r = m.build()
        c = r["club"]
        self.assertEqual(c["wins"], c["actual_wins"])
        self.assertEqual(c["losses"], c["actual_losses"])
        self.assertEqual(c["remaining_games"], 0)
        self.assertEqual(r["workloads"], [])
        self.assertEqual(c["range"]["low"], c["wins"])
        self.assertEqual(c["range"]["high"], c["wins"])

    def test_latest_roster_injury_changes_estimate(self):
        m = copy.copy(self.m)
        m.people = copy.deepcopy(self.m.people)
        p = next(p for p in m.people.values() if p["name"] == "Garrett Crochet")
        p.update(injured=True, injury_days=200)
        r = m.build()["club"]
        self.assertLess(r["expected_wins"], self.r["club"]["expected_wins"])
        self.assertLess(r["known_injury_win_effect"], 0)

    def test_exported_trade_changes_roster_forecast(self):
        m = copy.copy(self.m)
        m.people = copy.deepcopy(self.m.people)
        p = next(p for p in m.people.values() if p["name"] == "Garrett Crochet")
        p.update(team_id=1, org=1)
        self.assertLess(m.build()["club"]["expected_wins"], self.r["club"]["expected_wins"])

    def test_team_goals_and_locks_are_not_model_inputs(self):
        with patch(
            "frontoffice.office_state",
            side_effect=AssertionError("Preference state entered the forecast"),
        ):
            second = SeasonModel(self.m.d).build()
        self.assertEqual(second["club"]["expected_wins"], self.r["club"]["expected_wins"])
        self.assertTrue(all(math.isfinite(c["expected_wins"]) for c in second["league"]))


if __name__ == "__main__":
    unittest.main()
