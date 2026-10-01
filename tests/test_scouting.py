import unittest
from types import SimpleNamespace
from scouting import ScoutingReport,ranked


class ScoutingBenchmarks(unittest.TestCase):
    def fixture(self):
        players=[dict(id=1,kind='bat',team_id=1,position='2B',active=True,on_dl=False,injured=False,engine_value=6),
                 dict(id=2,kind='bat',team_id=1,position='2B',active=True,on_dl=False,injured=False,engine_value=10),
                 dict(id=3,kind='bat',team_id=2,position='2B',active=False,on_dl=True,injured=True,engine_value=5)]
        obj=ScoutingReport.__new__(ScoutingReport)
        obj.d=SimpleNamespace(team=1,base_year=2025,ratings={'players_fielding':{p['id']:{'fielding_rating_pos4':6} for p in players}})
        obj.o=SimpleNamespace(card=lambda p:dict(rating_component=p['engine_value']))
        obj.mlb=players;obj.starts={(1,4):130,(2,4):8,(3,4):120};obj._cohorts={}
        return obj,players

    def test_regulars_follow_usage_not_best_skill(self):
        obj,_=self.fixture();ps,method=obj.starters('2B')
        self.assertEqual([p['id'] for p in ps],[1,3])
        self.assertIn('not an exported depth chart',method)

    def test_injured_regular_remains_in_benchmark(self):
        obj,players=self.fixture()
        self.assertIn(players[2],obj.starters('2B')[0])
        self.assertEqual(obj.readiness(players[2],'2B')[0],'Unavailable')

    def test_tie_crossing_tenth_cannot_be_top_ten(self):
        result=ranked([9]*8+[6]*5+[4]*17,6)
        self.assertEqual((result['rank_low'],result['rank_high'],result['n']),(9,13,30))
        self.assertGreater(result['rank_high'],10)

    def test_missing_ratings_do_not_enter_cohort(self):
        result=ranked([None,0,4,6],6)
        self.assertEqual(result['n'],2)
        self.assertEqual(result['rank_low'],1)

    def test_potential_does_not_establish_readiness(self):
        obj,players=self.fixture();candidate=dict(players[0],active=False,team_id=9,engine_value=2,potential=10)
        self.assertEqual(obj.readiness(candidate,'2B')[0],'Future option')


if __name__=='__main__':unittest.main()
