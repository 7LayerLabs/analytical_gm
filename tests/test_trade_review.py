import unittest
from trade_review import trade_verdict,owner_goal_signal
class TradeDecisionRules(unittest.TestCase):
 def test_two_players_do_not_erase_unreplaced_core_cost(self):self.assertEqual(trade_verdict(True,False,.3,.2,'Win now'),'Decline this trade')
 def test_injury_patch_can_hide_recovery_loss(self):self.assertEqual(trade_verdict(False,True,.2,-.3,'Win now'),'Decline this trade')
 def test_improvement_can_receive_actionable_verdict(self):self.assertEqual(trade_verdict(False,True,.3,.2,'Win now'),'Worth pursuing')
 def test_neutral_package_needs_revision(self):self.assertEqual(trade_verdict(False,True,.02,0,'Win now'),'Revise the package')
 def test_missing_ratings_are_an_evidence_gap(self):self.assertEqual(trade_verdict(True,False,.2,.2,'Win now',True),'Needs more evidence')
class OwnerImpactRules(unittest.TestCase):
 def test_real_position_upgrade_is_green(self):self.assertEqual(owner_goal_signal('Position upgrade',0,0,False,[.5,.3])['signal'],'green')
 def test_unchanged_position_is_red_without_claiming_harm(self):
  r=owner_goal_signal('Position upgrade',0,0,False,[0,0]);self.assertEqual(r['signal'],'red');self.assertEqual(r['label'],'No demonstrated progress')
 def test_worse_position_is_red(self):self.assertEqual(owner_goal_signal('Position upgrade',0,0,False,[-.5,-.3])['label'],'Works against the goal')
 def test_split_tradeoff_is_amber(self):self.assertEqual(owner_goal_signal('Position upgrade',0,0,False,[.8,-.2])['signal'],'amber')
 def test_current_help_and_future_cost_can_have_different_colors(self):
  self.assertEqual(owner_goal_signal('Playoffs',.3,.2,True)['signal'],'green');self.assertEqual(owner_goal_signal('Championship window',.3,.2,True)['signal'],'red')
 def test_controlled_core_addition_can_support_long_window(self):self.assertEqual(owner_goal_signal('Championship window',.2,.1,False,core_gain=True)['signal'],'green')
 def test_unknown_popularity_chemistry_and_fan_response_are_not_invented(self):
  for category in ['Popularity','Chemistry','Fan interest']:self.assertEqual(owner_goal_signal(category,.3,.2,False)['signal'],'amber')
from storage import current
@unittest.skipUnless(current(),'Local export unavailable')
class TradeReviewLive(unittest.TestCase):
 def test_anthony_for_goodman_beck_is_a_decision_not_inventory(self):
  from department import department
  from frontoffice import evaluate
  d=department();ids={p['name']:p['id'] for p in d.profiles};before=d.by_id[ids['Roman Anthony']].copy()
  r=evaluate(d,{'type':'Trade','send':[ids['Roman Anthony']],'receive':[ids['Hunter Goodman'],ids['Jordan Beck']]});t=r['trade_review']
  self.assertEqual(r['recommendation'],'Decline this trade');self.assertIn('Keep Roman Anthony',t['lead']);self.assertEqual(len(t['comparisons']),2)
  self.assertTrue(all(not row['complete'] and 'Hunter Goodman' in row['unknown'] for row in t['financial'][1:]));self.assertEqual(d.by_id[ids['Roman Anthony']],before)
  self.assertTrue(all(x.get('signal') in ['red','green','amber'] for x in t['owner_impact']))
  self.assertTrue(any(x['jobs'] for x in t['people'] if x['side']=='Incoming'))
  if before['injured'] or before['on_dl']:self.assertNotEqual(t['comparisons'][0]['current_change'],t['comparisons'][0]['recovery_change'])
if __name__=='__main__':unittest.main()
