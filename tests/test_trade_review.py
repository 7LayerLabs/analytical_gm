import unittest
from trade_review import trade_verdict
class TradeDecisionRules(unittest.TestCase):
 def test_two_players_do_not_erase_unreplaced_core_cost(self):self.assertEqual(trade_verdict(True,False,.3,.2,'Win now'),'Decline this trade')
 def test_injury_patch_can_hide_recovery_loss(self):self.assertEqual(trade_verdict(False,True,.2,-.3,'Win now'),'Decline this trade')
 def test_improvement_can_receive_actionable_verdict(self):self.assertEqual(trade_verdict(False,True,.3,.2,'Win now'),'Worth pursuing')
 def test_neutral_package_needs_revision(self):self.assertEqual(trade_verdict(False,True,.02,0,'Win now'),'Revise the package')
 def test_missing_ratings_are_an_evidence_gap(self):self.assertEqual(trade_verdict(True,False,.2,.2,'Win now',True),'Needs more evidence')
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
  self.assertTrue(any(x['jobs'] for x in t['people'] if x['side']=='Incoming'))
  if before['injured'] or before['on_dl']:self.assertNotEqual(t['comparisons'][0]['current_change'],t['comparisons'][0]['recovery_change'])
if __name__=='__main__':unittest.main()
