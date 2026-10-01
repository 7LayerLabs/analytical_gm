import json, math, tempfile, unittest
from pathlib import Path
from datetime import date,timedelta
from types import SimpleNamespace
from unittest.mock import patch
from season_projection import base_runs,run_probability,park_counts,remaining_injury_games,SeasonModel,season_projection,VERSION
from department import department
from storage import current
import season_projection as model

class SeasonMath(unittest.TestCase):
    def test_missing_history_does_not_invent_wins(self):
        with self.assertRaisesRegex(ValueError,'completed MLB season'):SeasonModel(SimpleNamespace(base_bat={},base_pit={}))

    def test_each_matchup_has_exactly_one_expected_win(self):
        for a,b in [(4,4),(6,3),(1,7)]:self.assertAlmostEqual(run_probability(a,b)+run_probability(b,a),1)
        self.assertEqual(run_probability(4,4),.5)

    def test_more_runs_and_fewer_allowed_improve_expectation(self):
        self.assertGreater(run_probability(5,4),run_probability(4,4))
        self.assertGreater(run_probability(4,3),run_probability(4,4))

    def test_park_change_applies_by_batting_side(self):
        counts={'ab':100,'h':30,'d':5,'t':1,'hr':4}
        park={'hr_l':.8,'hr_r':1.2,'avg':1,'avg_l':1,'avg_r':1,'d':1,'t':1}
        self.assertAlmostEqual(park_counts(counts,park,'L')['hr'],3.2)
        self.assertAlmostEqual(park_counts(counts,park,'R')['hr'],4.8)

    def test_no_fake_absences_before_opening_day(self):
        start=date(2026,3,21);games=[start+timedelta(days=i) for i in [5,6,10,11]]
        self.assertEqual(remaining_injury_games({'injured':True,'injury_days':3},games,start),0)
        self.assertEqual(remaining_injury_games({'injured':True,'injury_days':10},games,start),2)
        self.assertEqual(remaining_injury_games({'injured':True,'injury_days':100},games,start,True),0)

    def test_opening_forecast_stays_fixed_across_new_exports(self):
        d=SimpleNamespace(sid='first',team=4,league=203,year=2026,manifest={'source_id':'test'})
        first={'snapshot':'first','preseason':True,'club':{'wins':89}}
        second={'snapshot':'second','preseason':False,'club':{'wins':81}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(model,'DATA',Path(tmp)),patch.object(model,'CACHE',{('first',VERSION):first,('second',VERSION):second}):
            initial=season_projection(d);self.assertEqual(initial['opening_forecast']['club']['wins'],89);json.dumps(initial)
            d.sid='second';r=season_projection(d)
            self.assertEqual(r['club']['wins'],81);self.assertEqual(r['opening_forecast']['club']['wins'],89)

    def test_midseason_capture_does_not_invent_preseason_baseline(self):
        d=SimpleNamespace(sid='late',team=4,league=203,year=2026,manifest={'source_id':'test'})
        with tempfile.TemporaryDirectory() as tmp,patch.object(model,'DATA',Path(tmp)),patch.object(model,'CACHE',{('late',VERSION):{'snapshot':'late','preseason':False}}):
            self.assertIsNone(season_projection(d)['opening_forecast'])
            self.assertEqual(list(Path(tmp).glob('*.json')),[])

@unittest.skipUnless(current(),'Requires a local OOTP export')
class LiveSeasonProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m=SeasonModel(department());cls.r=cls.m.build()

    def test_only_scheduled_clubs_and_balanced_wins(self):
        self.assertEqual(len(self.r['league']),30)
        self.assertAlmostEqual(sum(c['expected_wins'] for c in self.r['league']),len(self.m.games))
        self.assertEqual(sum(c['wins'] for c in self.r['league']),len(self.m.games))
        self.assertEqual(len(self.r['division']),5)

    def test_workload_totals_do_not_duplicate_team_season(self):
        for club in [self.m.club(self.m.d.team),self.m.club(self.m.d.team,True)]:
            self.assertAlmostEqual(sum(s['workload'] for s in club['shares'] if s['kind']=='bat'),club['games']*self.m.pa_per_game)
            self.assertAlmostEqual(sum(s['workload'] for s in club['shares'] if s['kind']=='pit'),club['games']*9)

    def test_run_environment_calibration_matches_export(self):
        b=self.m.d.base_bat
        self.assertAlmostEqual(base_runs(b,self.m.multiplier),b['r'],places=5)

    def test_team_goals_and_locks_are_not_model_inputs(self):
        with patch('frontoffice.office_state',side_effect=AssertionError('Preference state entered the forecast')):
            second=SeasonModel(self.m.d).build()
        self.assertEqual(second['club']['expected_wins'],self.r['club']['expected_wins'])
        self.assertTrue(all(math.isfinite(c['expected_wins']) for c in second['league']))

if __name__=='__main__':unittest.main()
