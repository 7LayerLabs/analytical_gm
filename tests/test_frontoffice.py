import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from frontoffice import Office,save,office_state,evaluate,percentile,assignment
from department import department
from storage import current
@unittest.skipUnless(current(), "Requires a local OOTP export")
class OfficeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d=department()
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'state.json';self.mock=patch('frontoffice.state_path',return_value=self.path);self.mock.start()
 def tearDown(self):self.mock.stop();self.tmp.cleanup()
 def test_ties_are_not_all_below(self):
  p=percentile([4,5,5,6],5);self.assertEqual((p['lower'],p['tied'],p['higher'],p['percentile']),(25,50,25,50))
 def test_assignment_does_not_take_scarce_player_greedily(self):
  self.assertEqual(assignment([[10,9],[10,-1000]]),[1,0])
 def test_actual_schedule_exposure(self):
  o=Office(self.d);self.assertEqual(o.parks['games'],162);self.assertEqual(o.parks['groups'],{'Home':81,'Division road':26,'Other road':55});self.assertAlmostEqual(sum(x['weight'] for x in o.parks['venues']),1)
 def test_blueprint_version_keeps_previous_plan(self):
  b=office_state(self.d)['blueprint'];b={**b,'identities':['moneyball','edgehunter'],'reason':'Test window change','seasons':{**b['seasons'],'2027':'Rebuild'}}
  r=save(self.d,{'action':'blueprint','blueprint':b});self.assertEqual(r['versions'][0]['before']['seasons']['2027'],'Win now');self.assertEqual(r['versions'][0]['snapshot'],self.d.sid)
 def test_lineup_lock_has_binding_slot_and_position(self):
  save(self.d,{'action':'lock','player_id':26081,'scope':'lineup','hand':'both','position':'LF','slot':4})
  for hand in ['vsr','vsl']:
   r=Office(self.d).roster(hand);p=next(x for x in r['lineup'] if x['player']['id']==26081);self.assertEqual((p['slot'],p['position'],p['locked']),(4,'LF',True));self.assertEqual(len({x['player']['id'] for x in r['lineup']}),len(r['lineup']))
 def test_trade_protection_requires_explicit_scenario_override(self):
  save(self.d,{'action':'lock','player_id':26081,'scope':'trade'})
  with self.assertRaises(ValueError):evaluate(self.d,{'type':'Trade','send':[26081],'receive':[]})
  r=evaluate(self.d,{'type':'Trade','send':[26081],'receive':[next(p['id'] for p in self.d.profiles if p['league_id']==self.d.league and p['organization_id']!=self.d.team and p['team_id']!=self.d.team)],'override':True});self.assertFalse(r['locks_respected']);self.assertEqual(len(office_state(self.d)['locks']),1)
 def test_injured_lock_is_visible_and_preserved(self):
  p=next(p for p in self.d.own() if p['injured'] and p['kind']=='bat')
  save(self.d,{'action':'lock','player_id':p['id'],'scope':'lineup','position':'DH'})
  r=Office(self.d).roster();self.assertFalse(r['ready_for_review']);self.assertTrue(any(p['name'] in w for w in r['warnings']));self.assertEqual(len(office_state(self.d)['locks']),1)
 def test_internal_roster_is_bounded_and_unique(self):
  r=Office(self.d).roster(internal=True);self.assertLessEqual(r['selected_count'],26);self.assertLessEqual(len(r['bullpen']),8);self.assertLessEqual(len(r['bench']),4)
  ids=[x['player']['id'] for x in r['lineup']]+[x['player']['id'] for x in r['rotation'] if x['player']]+[x['player']['id'] for x in r['bullpen']]+[x['id'] for x in r['bench']];self.assertEqual(len(ids),len(set(ids)))
 def test_contract_options_and_crochet_arbitration(self):
  o=Office(self.d);c=next(p for p in self.d.own() if p['name']=='Garrett Crochet');self.assertEqual(o.card(c)['end_year'],2032);self.assertNotIn(c['id'],[p['id'] for p in o.finances()['arbitration_review']]);self.assertTrue(any('option' in r['type'] for r in o.contract_schedule(self.d.by_id[26081])))
 def test_case_save_preserves_snapshot_and_blueprint(self):
  s=save(self.d,{'action':'decision','case':{'type':'Replacement','position':'P','question':'Replace injured starter'}});case=s['decisions'][0];self.assertEqual(case['snapshot'],self.d.sid);self.assertEqual(case['status'],'Exploring');self.assertEqual(case['report']['alternatives'][0]['name'],'Do nothing')
 def test_extension_overlap_is_flagged(self):
  p=next(p for p in self.d.own() if p['name']=='Garrett Crochet');r=evaluate(self.d,{'type':'Extension','player_id':p['id'],'annual_offer':30000000,'offer_years':3,'start_year':2027});self.assertEqual(r['offer_total'],90000000);self.assertTrue(r['overlap']);self.assertTrue(any('overlap' in s for s in r['checks']))
 def test_checkpoint_is_real_capture(self):
  s=save(self.d,{'action':'checkpoint','label':'Opening season'});self.assertEqual(s['checkpoints'][0]['snapshot'],self.d.sid);self.assertEqual(s['checkpoints'][0]['game_date'],str(self.d.manifest['game_date']))
if __name__=='__main__':unittest.main()

@unittest.skipUnless(current(), "Requires a local OOTP export")
class AdditionalOfficeChecks(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d=department()
 def test_replacement_does_not_recommend_current_rotation(self):
  o=Office(self.d);assigned={x['player']['id'] for x in o.roster()['rotation'] if x['player']};r=evaluate(self.d,{'type':'Replacement','position':'P'});self.assertTrue(all(x['id'] not in assigned for x in r['internal']))
 def test_scenario_does_not_change_live_direction(self):
  before=office_state(self.d)['blueprint'];r=evaluate(self.d,{'type':'Deadline plan','scenario_mode':'Selective sell'});self.assertEqual(r['scenario_mode'],'Selective sell');self.assertEqual(before,office_state(self.d)['blueprint'])
 def test_signed_extension_replaces_overlapping_year(self):
  import department as module
  original=module.records
  def amended(con,sql,params=None):
   rs=original(con,sql,params)
   if sql=='select * from players_contract_extension':rs=[x for x in rs if x['player_id']!=26081]+[{'player_id':26081,'season_year':2026,'years':3,'salary0':12000000,'salary1':14000000,'salary2':16000000}]
   return rs
  with patch('department.records',side_effect=amended):d=module.Department(self.d.sid)
  self.assertEqual(d.by_id[26081]['salary'],12000000);self.assertEqual(d.by_id[26081]['salaries'][2027],14000000)
  self.assertEqual(Office(d).card(d.by_id[26081])['end_year'],2028)
