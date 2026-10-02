import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from owner_goals import validate_goals,owner_context,owner_board
from storage import current
class OwnerRules(unittest.TestCase):
 def test_invalid_status_is_rejected(self):
  with self.assertRaises(ValueError):validate_goals({'year':2026,'goals':[{'title':'Win','status':'Automatically completed'}]})
 def test_future_deadline_is_preserved(self):
  year,entry=validate_goals({'year':2026,'goals':[{'title':'Championship','category':'Championship window','due_year':2029}]});self.assertEqual(entry['goals'][0]['due_year'],2029)
 def test_multi_year_priority_carries_forward_but_annual_goal_expires(self):
  o=SimpleNamespace(d=SimpleNamespace(year=2027),state={'owner_goals':{'2026':{'goals':[{'title':'Playoffs','category':'Playoffs','due_year':2026,'status':'Not assessed'},{'title':'Championship','category':'Championship window','due_year':2029,'status':'In progress'}]}}})
  self.assertEqual([g['title'] for g in owner_context(o)['goals']],['Championship'])
@unittest.skipUnless(current(),'Local export unavailable')
class OwnerLive(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from department import department
  cls.d=department()
 def test_save_archive_baseline_and_decision_context(self):
  from frontoffice import save,Office,office_state,evaluate
  with tempfile.TemporaryDirectory() as tmp,patch('frontoffice.state_path',return_value=Path(tmp)/'state.json'):
   b={'action':'owner-goals','year':self.d.year,'owner':'John Henry','goals':[{'id':'2b','title':'Upgrade at Second Base','category':'Position upgrade','position':'2B'}]}
   first=save(self.d,b);baseline=first['owner_goals'][str(self.d.year)]['baseline'];b['goals'][0]['notes']='Reviewed current starter';b['goals'][0]['status']='In progress';second=save(self.d,b)
   self.assertEqual(second['owner_goals'][str(self.d.year)]['baseline'],baseline);self.assertEqual(len(second['owner_goal_history']),2)
   self.assertEqual(owner_board(Office(self.d))['evidence']['fan_change'],self.d.financials[self.d.team]['fan_interest_visible']-baseline['fan_interest'])
   report=evaluate(self.d,{'type':'Replacement','position':'2B'});self.assertEqual(report['owner_goals']['goals'][0]['position'],'2B')
   self.assertEqual(office_state(self.d)['blueprint']['seasons'][str(self.d.year)],'Win now')
if __name__=='__main__':unittest.main()
