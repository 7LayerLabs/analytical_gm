import sys,unittest,math,json,csv,tempfile
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import batting,pitching,projection,fip_constant
from department import department,arbitration_review_candidate
from storage import connect,records,import_snapshot,current
from jev import validate_response,questions,crypt
import storage
from analytics import BAT_FIELDS,PIT_FIELDS

class BaseballMath(unittest.TestCase):
    def test_obp_and_extra_bases(self):
        r=batting({'ab':100,'h':25,'d':5,'t':1,'hr':4,'bb':10,'hp':2,'sf':3,'pa':115,'k':20})
        self.assertEqual(r['avg'],.25);self.assertEqual(r['slg'],.44);self.assertEqual(r['iso'],.19)
        self.assertEqual(r['obp'],round(37/115,3));self.assertEqual(r['ops'],round(37/115+.44,3))
    def test_outs_and_fip(self):
        r=pitching({'outs':17,'er':2,'hra':1,'bb':3,'iw':1,'hp':1,'k':8,'bf':25},3.1)
        self.assertEqual(r['ip_display'],'5.2');self.assertEqual(r['era'],round(18/(17/3),2))
        self.assertEqual(r['fip'],round((13+3*(3-1+1)-16)/(17/3)+3.1,2))
    def test_empty_is_unknown(self):
        self.assertIsNone(batting({})['ops']);self.assertIsNone(pitching({})['era'])
    def test_no_future_leakage(self):
        league={'pa':1000,'ab':880,'h':220,'d':40,'t':5,'hr':30,'bb':90,'hp':15,'sf':10,'k':200}
        history=[{'year':2025,**league},{'year':2026,**league,'hr':500}]
        self.assertEqual(projection(history,2026,league,'bat'),projection(history[:1],2026,league,'bat'))
    def test_prior_for_no_history(self):
        l={'pa':1000,'ab':880,'h':220,'d':40,'t':5,'hr':30,'bb':90,'hp':15,'sf':10,'k':200}
        p=projection([],2026,l,'bat');self.assertEqual(p['evidence'],'League prior');self.assertEqual(p['prior_weight'],1)
        self.assertEqual(p['ops'],batting(l)['ops'])
    def test_workload_changes_counts_not_rates(self):
        l={'pa':1000,'ab':880,'h':220,'d':40,'t':5,'hr':30,'bb':90,'hp':15,'sf':10,'k':200}
        a=projection([],2026,l,'bat',200);b=projection([],2026,l,'bat',600)
        self.assertEqual(a['ops'],b['ops']);self.assertEqual(b['hr'],3*a['hr'])

@unittest.skipUnless(current(), "Requires a local OOTP export")
class LiveSaveChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.d=department()
    def test_season_totals_exclude_splits(self):
        with connect() as c:
            manual=records(c,'select sum(h) h,sum(hr) hr from players_career_batting_stats where league_id=203 and year=2025 and split_id=1 and game_id=0')[0]
            summed=records(c,'select sum(h) h,sum(hr) hr from bat_seasons where league_id=203 and year=2025')[0]
        self.assertEqual(manual,summed);self.assertEqual(manual['h'],40138)
    def test_contract_start_year(self):
        d=self.d;sonny=next(p for p in d.own() if p['name']=='Sonny Gray')
        self.assertEqual(sonny['salary'],21000000);self.assertEqual(sonny['salaries'][2027],25000000)
    def test_crochet_not_arbitration_candidate(self):
        d=self.d;crochet=next(p for p in d.own() if p['name']=='Garrett Crochet')
        self.assertEqual(max(crochet['salaries']),2032)
        self.assertNotIn(crochet['id'],[p['id'] for p in d.finances()['arbitration_review']])
    def test_lineups_unique(self):
        for hand in ('vsr','vsl'):
            l=self.d.lineup(hand)['lineup'];ids=[s['player']['id'] for s in l]
            self.assertEqual(len(ids),len(set(ids)));self.assertEqual(len(l),9)
    def test_no_roster_mutations(self):
        pid=self.d.own()[0]['id'];p=self.d.player(pid)
        self.assertEqual(p['source']['snapshot'],current()['id']);self.assertTrue(p['why'])
    def test_package_payroll(self):
        send=self.d.own()[0];receive=self.d.acquisition()['players'][0]
        s=self.d.scenario([send['id']],[receive['id']]);self.assertEqual(s['years'][0]['payroll_change'],receive['salary']-send['salary'])
        with self.assertRaises(ValueError):self.d.scenario([send['id']],[send['id']])
    def test_unchanged_import_is_noop(self):
        before=current()['id'];self.assertEqual(import_snapshot()['id'],before)
    def test_backtest_evidence(self):
        q=self.d.quality()
        for kind in ('bat','pit'):
            self.assertEqual(len(q['backtests'][kind]),4)
            self.assertTrue(all(r['players']>100 for r in q['backtests'][kind]))
        for band in q['ranges'].values():
            self.assertGreater(band['calibration_players'],500)
            self.assertTrue(0<=band['held_out_coverage']<=1)
    def test_staff_assignments_unique(self):
        staff=self.d.pitching_plan();ids=[s['player']['id'] for s in staff['rotation']+staff['bullpen']]
        self.assertEqual(len(ids),len(set(ids)))
    def test_bad_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):department('../outside')

class JevContract(unittest.TestCase):
    def valid(self):
        qs=questions('pit')
        return qs,{'answers':{k:{'type':'choice','choice':'review','confidence':.1,'probabilities':{option:(1 if option=='review' else 0) for option in q['criteria']}} for k,q in qs.items()}}
    def test_typed_response(self):
        qs,r=self.valid();self.assertEqual(validate_response(r,qs),r)
    def test_invalid_option(self):
        qs,r=self.valid();r['answers']['role']['choice']='invented'
        with self.assertRaises(ValueError):validate_response(r,qs)
    def test_nan_rejected(self):
        qs,r=self.valid();r['answers']['role']['confidence']=math.nan
        with self.assertRaises(ValueError):validate_response(r,qs)
    @unittest.skipUnless(sys.platform=='win32','Windows encryption test')
    def test_windows_key_roundtrip(self):
        sample=b'non-secret-test-value';encrypted=crypt(sample)
        self.assertNotEqual(sample,encrypted);self.assertEqual(crypt(encrypted,True),sample)

class ArbitrationReview(unittest.TestCase):
    def setUp(self):self.p={'secondary':True,'free_agent':False,'service_years':4}
    def test_expiring_single_year_can_be_reviewed(self):
        self.assertTrue(arbitration_review_candidate(self.p,{'season_year':2026,'years':1},{},2027))
    def test_multiyear_deal_excluded(self):
        self.assertFalse(arbitration_review_candidate(self.p,{'season_year':2026,'years':7},{},2027))
    def test_signed_extension_excluded(self):
        self.assertFalse(arbitration_review_candidate(self.p,{'season_year':2026,'years':1},{'season_year':2027,'years':3},2027))
    def test_service_threshold_and_free_agency(self):
        self.assertFalse(arbitration_review_candidate({**self.p,'service_years':2},{},{},2027))
        self.assertFalse(arbitration_review_candidate({**self.p,'service_years':6},{},{},2027))
        self.assertFalse(arbitration_review_candidate({**self.p,'free_agent':True},{},{},2027))

class ImportSafety(unittest.TestCase):
    def fixture(self,folder):
        source=folder/'source';source.mkdir(); data=folder/'data';data.mkdir()
        for table,required in storage.REQUIRED.items():
            fields=list(required)
            if table=='players_career_batting_stats':fields+=['game_id']+BAT_FIELDS
            if table=='players_career_pitching_stats':fields+=['game_id']+PIT_FIELDS
            fields=list(dict.fromkeys(fields));row={k:0 for k in fields}
            row.update({k:v for k,v in {'player_id':1,'team_id':4,'organization_id':4,'league_id':203,'year':2025,'split_id':1,'season_year':2026,'current_date':'2026-3-21','first_name':'Test','last_name':'Player'}.items() if k in fields})
            with open(source/(table+'.csv'),'w',newline='',encoding='utf-8') as h:
                writer=csv.DictWriter(h,fieldnames=fields);writer.writeheader();writer.writerow(row)
        return source,data
    def test_changed_source_rejected_and_prior_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,data=self.fixture(Path(tmp))
            cfg={'csv_directory':str(source),'team_id':4,'league_id':203}
            with patch.object(storage,'DATA',data),patch.object(storage,'config',return_value=cfg):
                first=storage.import_snapshot();sig=storage.signature();changed=sig+[('changed.csv',1,1)]
                with patch.object(storage,'signature',side_effect=[sig,changed]):
                    with self.assertRaisesRegex(ValueError,'changed during import'):storage.import_snapshot(force=True)
                self.assertEqual(storage.current()['id'],first['id'])
                self.assertEqual(len(list(data.glob('*/manifest.json'))),1)
    def test_missing_header_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,data=self.fixture(Path(tmp));(source/'players.csv').write_text('player_id\n1\n')
            with patch.object(storage,'DATA',data),patch.object(storage,'config',return_value={'csv_directory':str(source),'team_id':4,'league_id':203}):
                with self.assertRaisesRegex(ValueError,'missing columns'):storage.import_snapshot()
                self.assertIsNone(storage.current())

if __name__=='__main__':unittest.main()
