import bisect, collections, json, threading
import re
from datetime import datetime, timezone
from analytics import *
from storage import *

MODEL_LOCK=threading.Lock(); CACHE={}

def index(rows,key='player_id'):return {int(r[key]):r for r in rows}

def contract_covers_year(contract,year):
    start=int(number(contract.get('season_year')))
    years=int(number(contract.get('years')))
    return start>0 and years>0 and start<=year<start+years

def arbitration_review_candidate(player,contract,extension,year,minimum_service=3,free_agency_service=6):
    service=number(player.get('service_years'))
    return (bool(player.get('secondary')) and not player.get('free_agent')
            and minimum_service<=service<free_agency_service
            and not contract_covers_year(contract,year)
            and not contract_covers_year(extension,year))

class Department:
    def __init__(self,sid=None):
        self.manifest=current() if sid is None else read_json(DATA/sid/'manifest.json')
        if not self.manifest:raise ValueError('No imported snapshot yet.')
        self.sid=self.manifest['id']; self.year=self.manifest['season']; self.team=self.manifest['team_id']; self.league=self.manifest['league_id']
        with connect(self.sid) as con:
            self.teams=index(records(con,'select * from teams'),'team_id')
            self.leagues=index(records(con,'select * from leagues'),'league_id')
            self.financials=index(records(con,'select * from team_financials'),'team_id')
            self.parks=index(records(con,'select * from parks'),'park_id')
            self.raw=index(records(con,'select * from players where retired=0 and person_type=0'))
            self.ratings={t:index(records(con,f'select * from {t}')) for t in ['players_batting','players_pitching','players_fielding','players_value']}
            self.contracts=index(records(con,'select * from players_contract'))
            self.extensions=index(records(con,'select * from players_contract_extension'))
            self.roster=index(records(con,'select * from players_roster_status'))
            self.hist={}; self.baselines={}
            for kind,table,fields in [('bat','bat_seasons',BAT_FIELDS),('pit','pit_seasons',PIT_FIELDS)]:
                rows=records(con,f'select * from {table} where league_id=? and year>=2019 and year<?',[self.league,self.year+1])
                grouped=collections.defaultdict(list); annual=collections.defaultdict(list)
                for r in rows:grouped[int(r['player_id'])].append(r);annual[int(r['year'])].append(r)
                self.hist[kind]=grouped;self.baselines[kind]={y:combine(rs,fields) for y,rs in annual.items()}
            self.splits=collections.defaultdict(list)
            for r in records(con,'select * from players_career_batting_stats where league_id=? and year>=? and split_id in (2,3)',[self.league,self.year-3]):
                self.splits[int(r['player_id'])].append(r)
        self.base_year=max((y for y in self.baselines['bat'] if y<self.year),default=self.year-1)
        self.base_bat=self.baselines['bat'].get(self.base_year,{})
        self.base_pit=self.baselines['pit'].get(self.base_year,{})
        self.fip_c=fip_constant(self.base_pit)
        self.profiles=[]; self.by_id={}
        mlb_orgs={tid for tid,t in self.teams.items() if t['league_id']==self.league and t['level']==1 and not t.get('allstar_team')}
        eligible=[p for p in self.raw.values() if int(p.get('organization_id') or 0) in mlb_orgs or int(p.get('league_id') or 0)==self.league or int(p.get('organization_id') or 0)==self.team or int(p.get('free_agent') or 0)==1 or int(p.get('draft_eligible') or 0)==1]
        # Percentiles are relative to currently assigned MLB players, by hitter/pitcher cohort.
        cohorts={'bat':[], 'pit':[]}
        for p in self.raw.values():
            if int(p.get('league_id') or 0)==self.league:
                pid=int(p['player_id']);kind='pit' if int(p.get('position') or 0)==1 else 'bat'
                val=number(self.ratings['players_value'].get(pid,{}).get('overall_value'))
                cohorts[kind].append(val)
        for values in cohorts.values():values.sort()
        for p in eligible:
            pid=int(p['player_id']);kind='pit' if int(p.get('position') or 0)==1 else 'bat'
            hist=self.hist[kind].get(pid,[]); latest=next((r for r in hist if r['year']==self.year and number(r.get('bf' if kind=='pit' else 'pa'))>0),None) or next((r for r in hist if r['year']==self.base_year),None)
            recent=latest or (max(hist,key=lambda r:r['year']) if hist else {})
            observed=(pitching(recent,self.fip_c) if kind=='pit' else batting(recent)) if recent else None
            forecast=projection(hist,self.year,self.base_pit if kind=='pit' else self.base_bat,kind)
            c=self.contracts.get(pid,{})
            salaries=self.salary_schedule(c)
            # Signed extension replaces an overlapping scheduled year; do not add it twice.
            salaries.update(self.salary_schedule(self.extensions.get(pid,{})))
            value=self.ratings['players_value'].get(pid,{})
            oa=number(value.get('overall_value')); cohort=cohorts[kind]
            pct=round(100*bisect.bisect_right(cohort,oa)/len(cohort)) if cohort else None
            rt=self.roster.get(pid,{})
            teamid=int(p.get('team_id') or 0)
            profile={'id':pid,'name':f"{p['first_name']} {p['last_name']}",'age':p['age'],'position':POSITIONS.get(int(p.get('position') or 0),'Other'),
                'role_code':p.get('role'),'kind':kind,'team_id':teamid,'team':self.team_name(teamid),'league_id':p.get('league_id'),
                'organization_id':p.get('organization_id'),'bats':{1:'R',2:'L',3:'S'}.get(p.get('bats'),'?'),
                'throws':{1:'R',2:'L'}.get(p.get('throws'),'?'),'injured':bool(p.get('injury_is_injured')),
                'injury_days':p.get('injury_left'),'free_agent':bool(p.get('free_agent')),'draft_eligible':bool(p.get('draft_eligible')),
                'active':bool(rt.get('is_active')),'secondary':bool(rt.get('is_on_secondary')),
                'on_dl':bool(rt.get('is_on_dl')),'on_waivers':bool(rt.get('is_on_waivers')),'dfa':bool(rt.get('designated_for_assignment')),
                'options_used':rt.get('options_used'),'service_years':rt.get('mlb_service_years'),
                'salary':salaries.get(self.year,0),'salaries':salaries,'contract_years':c.get('years',0),'no_trade':bool(c.get('no_trade')),
                'salary_known':self.year in salaries,
                'recorded':observed,'recorded_year':recent.get('year'),'projection':forecast,'engine_percentile':pct,
                'engine_value':oa,'engine_potential':number(value.get('talent_value')),
                'score':forecast.get('quality_index',forecast.get('ops_index',100))}
            self.profiles.append(profile);self.by_id[pid]=profile
        self.profiles.sort(key=lambda p:(p['engine_percentile'] or 0,p['score']),reverse=True)

    def team_name(self,tid):
        t=self.teams.get(tid,{})
        return (str(t.get('name',''))+' '+str(t.get('nickname',''))).strip() or ('Free agent' if not tid else str(tid))

    def salary_schedule(self,c):
        # salary0 is first contract year, season_year is starting year; current_year is a zero-based index.
        start=int(number(c.get('season_year')));years=int(number(c.get('years')))
        return {start+i:number(c.get(f'salary{i}')) for i in range(min(years,15)) if start+i>=self.year}

    def own(self):return [p for p in self.profiles if p['organization_id']==self.team or p['team_id']==self.team]
    def active(self):return [p for p in self.own() if p['team_id']==self.team and p['active'] and not p['on_dl'] and not p['injured']]

    def briefing(self):
        active=self.active(); own=self.own(); rules=self.leagues[self.league]; fin=self.financials[self.team]; needs=self.depth()
        items=[]
        for p in own:
            if p['dfa'] or p['on_waivers']:
                items.append({'title':f"Review {p['name']}'s roster status",'detail':'Export marks this player designated for assignment or on waivers. Check the game for the applicable deadline.','player_id':p['id'],'priority':'Urgent'})
        injured=[p for p in own if p['injured'] or p['on_dl']]
        if injured:items.append({'title':f'{len(injured)} players need health review','detail':', '.join(p['name'] for p in injured[:6]),'priority':'Review'})
        limit=int(rules['rules_active_roster_limit'])
        if len(active)!=limit:items.append({'title':f'{len(active)} healthy active players for {limit} spots','detail':'Preseason rosters may differ from regular-season limits. Check assignments before Opening Day.','priority':'Review'})
        for n in needs:
            if n['position'] in ('P',):continue
            if not n['players']:items.append({'title':f"No established {n['position']} coverage",'detail':'No healthy active player has an exported position rating of at least 4. Consider a position change, promotion or acquisition.','priority':'Review'})
        if len([p for p in active if p['kind']=='pit'])<12:items.append({'title':'Check pitching workload coverage','detail':'Fewer than 12 healthy pitchers are marked active. Review your rotation, bullpen and injury replacements.','priority':'Review'})
        expiring=[p for p in own if p['salary']>0 and not any(int(y)>self.year and s>0 for y,s in p['salaries'].items())]
        if expiring:items.append({'title':f'{len(expiring)} paid contracts have no exported future salary','detail':'Check arbitration, extensions and options before treating these players as free agents.','priority':'Planning'})
        thin=[p for p in active if p['projection']['evidence']!='Established']
        if thin:items.append({'title':f'{len(thin)} active players have limited MLB projection evidence','detail':'Use ratings and minor-league history alongside their league-prior forecasts.','priority':'Evidence'})
        if not items:items.append({'title':'No roster flags from this snapshot','detail':'Review depth, payroll and projections before advancing the game.','priority':'Review'})
        return {'items':items,'active':len(active),'secondary':sum(p['secondary'] for p in own if p['team_id']==self.team),
                'injured':len(injured),'organization':len(own),'payroll':fin['player_payroll'],'budget':fin['budget'],
                'rules':{'active':limit,'secondary':rules['rules_secondary_roster_limit']},
                'team':self.team_name(self.team),'base_year':self.base_year}

    def depth(self):
        own=self.own(); active=self.active();result=[]
        for pos in [2,3,4,5,6,7,8,9,10,1]:
            key=f'fielding_rating_pos{pos}'
            if pos==1:candidates=[p for p in active if p['kind']=='pit']
            elif pos==10:candidates=[p for p in active if p['kind']=='bat']
            else:candidates=[p for p in active if p['kind']=='bat' and number(self.ratings['players_fielding'].get(p['id'],{}).get(key))>=4]
            candidates=sorted(candidates,key=lambda p:p['score'],reverse=True)
            reserves=[p for p in own if p not in active and not p['injured'] and (p['kind']=='pit' if pos==1 else p['kind']=='bat' and (pos==10 or number(self.ratings['players_fielding'].get(p['id'],{}).get(key))>=4))]
            reserves.sort(key=lambda p:p['engine_percentile'] or 0,reverse=True)
            result.append({'position':POSITIONS[pos],'players':[{'id':p['id'],'name':p['name'],'score':p['score'],'defense':self.ratings['players_fielding'].get(p['id'],{}).get(key)} for p in candidates[:5]],
                           'reserves':[{'id':p['id'],'name':p['name'],'team':p['team']} for p in reserves[:3]]})
        return result

    def lineup(self,hand='vsr'):
        if hand not in ('vsr','vsl'):raise ValueError('Choose vsr or vsl')
        hitters=[p for p in self.active() if p['kind']=='bat'];used=set();selected=[]
        def rating_score(p):
            r=self.ratings['players_batting'].get(p['id'],{});prefix='batting_ratings_'+hand+'_'
            return sum(number(r.get(prefix+k))*w for k,w in [('contact',0.3),('power',0.35),('eye',0.25),('strikeouts',0.1)])
        # Fill scarce defensive positions first; deterministic heuristic, not game strategy optimization.
        for pos in [2,6,8,4,5,9,7,3,10]:
            options=[p for p in hitters if p['id'] not in used and (pos==10 or number(self.ratings['players_fielding'].get(p['id'],{}).get(f'fielding_rating_pos{pos}'))>=4)]
            if not options:selected.append({'position':POSITIONS[pos],'player':None});continue
            best=max(options,key=rating_score);used.add(best['id']);selected.append({'position':POSITIONS[pos],'player':best,'fit_score':round(rating_score(best),2)})
        filled=[s for s in selected if s['player']]
        filled.sort(key=lambda s:rating_score(s['player']),reverse=True)
        # OBP-style ratings choose leadoff among first five; strongest remaining bats occupy 2-4.
        if filled:
            leadoff=max(filled[:5],key=lambda s:number(self.ratings['players_batting'].get(s['player']['id'],{}).get('batting_ratings_'+hand+'_eye')))
            filled.remove(leadoff);filled.insert(0,leadoff)
        return {'hand':hand,'lineup':filled,'unfilled':[s['position'] for s in selected if not s['player']],
                'explanation':'Heuristic: position ratings ≥4; fill C/SS/CF first, then rank platoon contact, power, eye and avoid-K ratings. No claim of optimized runs.'}

    def pitching_plan(self):
        pitchers=[p for p in self.active() if p['kind']=='pit'];rotation=[];bullpen=[]
        for p in pitchers:
            r=self.ratings['players_pitching'].get(p['id'],{});stamina=number(r.get('pitching_ratings_misc_stamina'))
            repertoire=sum(number(v)>=4 for k,v in r.items() if k.startswith('pitching_ratings_pitches_') and 'talent' not in k)
            seasons=self.hist['pit'].get(p['id'],[]);recent=max(seasons,key=lambda s:s['year']) if seasons else {}
            start_share=ratio(number(recent.get('gs')),number(recent.get('g')))
            candidate=stamina>=5 and (repertoire>=3 or (start_share is not None and start_share>=.5))
            item={'player':p,'stamina':stamina,'qualifying_pitches':repertoire,'recent_start_share':start_share,
                  'reason':f'Stamina {stamina:g}; {repertoire} pitches rated ≥4; '+(f'{round(start_share*100)}% of latest MLB appearances were starts.' if start_share is not None else 'no MLB usage history.')}
            (rotation if candidate else bullpen).append(item)
        rotation.sort(key=lambda x:x['player']['score'],reverse=True)
        bullpen+=rotation[5:];rotation=rotation[:5];bullpen.sort(key=lambda x:x['player']['score'],reverse=True)
        for i,item in enumerate(bullpen):item['suggested_role']='High leverage' if i<2 else 'Middle relief / depth'
        return {'rotation':rotation,'bullpen':bullpen,'unfilled':max(0,5-len(rotation)),
                'note':'Heuristic role plan from stamina, repertoire, recorded usage and projected FIP. It does not assess fatigue, recovery, pitch mix outcomes or optimal leverage deployment.'}

    def player(self,pid,workload=None):
        if workload is not None and (not math.isfinite(workload) or not 0<workload<=800):raise ValueError('Use a positive workload of at most 800.')
        p=self.by_id.get(pid)
        if not p:raise ValueError('Player is not in the current analysis cohort.')
        with connect(self.sid) as con:
            histories={}
            for kind,table in [('bat','bat_seasons'),('pit','pit_seasons')]:
                rs=records(con,f'select * from {table} where player_id=? order by year desc,league_id',[pid])
                histories[kind]=[{**r,**(batting(r) if kind=='bat' else pitching(r,self.fip_c)),
                                  'league':self.leagues.get(int(r['league_id']),{}).get('abbr',str(r['league_id']))} for r in rs]
            fielding=records(con,'select * from players_career_fielding_stats where player_id=? order by year desc limit 40',[pid])
        ratings={t:self.ratings[t].get(pid,{}) for t in self.ratings}
        splits=[{**r,**batting(r),'split_label':f"Export split {r['split_id']} (handedness label unverified)"} for r in self.splits.get(pid,[])]
        forecast=p['projection'] if workload is None else projection(self.hist[p['kind']].get(pid,[]),self.year,self.base_pit if p['kind']=='pit' else self.base_bat,p['kind'],workload)
        ranges=self.quality()['ranges'];band=ranges.get(p['kind']);history=self.hist[p['kind']].get(pid,[])
        relevant=[s for s in history if self.year-3<=s['year']<self.year]
        exposure=sum(number(s.get('pa' if p['kind']=='bat' else 'outs')) for s in relevant)
        interval=None
        if band and exposure>=(100 if p['kind']=='bat' else 90):
            value=forecast[band['metric']]
            interval={**band,'low':rounded(max(0,value+band['low_residual']),3 if p['kind']=='bat' else 2),
                      'high':rounded(value+band['high_residual'],3 if p['kind']=='bat' else 2)}
        reasons=[]
        if p['recorded']:
            r=p['recorded'];reasons.append(f"Recorded {p['recorded_year']} MLB {'FIP '+str(r['fip'])+'; K–BB% '+str(round((r['k_bb_pct'] or 0)*100,1)) if p['kind']=='pit' else 'OPS '+str(r['ops'])+'; OBP '+str(r['obp'])}.")
        reasons.append(f"Projection uses {forecast['observed_exposure']} MLB {'batters faced' if p['kind']=='pit' else 'plate appearances'} from the three prior seasons; league prior weight {round(100*forecast['prior_weight'])}%.")
        reasons.append(f"Game-engine current value is at the {p['engine_percentile']}th percentile of current MLB {'pitchers' if p['kind']=='pit' else 'hitters'}. This is an engine comparison, not a performance probability.")
        if p['injured']:reasons.append('Currently injured: workload scenario does not reduce for injury.')
        if p['no_trade']:reasons.append('Exported no-trade clause; verify permission before a trade.')
        return {'player':p,'projection':forecast,'histories':histories,'ratings':ratings,'splits':splits,'fielding':fielding,
                'contract':self.contracts.get(pid,{}),'extension':self.extensions.get(pid,{}),'roster':self.roster.get(pid,{}),
                'raw':self.raw[pid],'why':reasons,'interval':interval,'park':self.parks.get(self.teams.get(self.team,{}).get('park_id'),{}),
                'source':{'snapshot':self.sid,'date':self.manifest['game_date'],'model':VERSION}}

    def finances(self):
        own=self.own();fin=self.financials[self.team];years=[]
        for year in range(self.year,self.year+7):
            entries=[]
            for p in own:
                amount=p['salaries'].get(year,0)
                if amount:entries.append({'id':p['id'],'name':p['name'],'salary':amount})
            entries.sort(key=lambda x:x['salary'],reverse=True)
            years.append({'year':year,'scheduled_salary':sum(e['salary'] for e in entries),'players':len(entries),'entries':entries})
        current_sum=years[0]['scheduled_salary'];reconciliation=number(fin.get('player_payroll'))-current_sum
        review_year=self.year+1;rules=self.leagues[self.league]
        arbitration=[p for p in own if arbitration_review_candidate(p,self.contracts.get(p['id'],{}),self.extensions.get(p['id'],{}),review_year,
                      number(rules.get('rules_salary_arbitration_minimum_years'),3),number(rules.get('rules_fa_minimum_years'),6))]
        return {'financials':fin,'years':years,'reconciliation_difference':reconciliation,'arbitration_review':arbitration,'arbitration_review_year':review_year,
                'note':'Salary schedule follows contract start year. Future options remain included as scheduled amounts, not guaranteed commitments. Arbitration, renewals, retained salary and bonuses may explain differences from game payroll. No automated arbitration dollar estimate.'}

    def development(self):
        prospects=[p for p in self.own() if p['team_id']!=self.team or p['age']<=25]
        prospects.sort(key=lambda p:p['engine_potential'],reverse=True)
        previous=[m for m in snapshots() if m['id']!=self.sid and m['created_at']<self.manifest['created_at']]
        changes=[]
        if previous:
            with connect(previous[0]['id']) as con:
                old=index(records(con,'select player_id,overall_value,talent_value from players_value'))
            for p in prospects:
                before=old.get(p['id'])
                if before:
                    delta=p['engine_value']-number(before['overall_value'])
                    potential=p['engine_potential']-number(before['talent_value'])
                    if delta or potential:changes.append({'id':p['id'],'name':p['name'],'current_change':delta,'potential_change':potential})
        return {'prospects':prospects,'changes':changes,'previous_snapshot':previous[0]['id'] if previous else None,
                'note':'Ranks use exported engine talent values. Promotion candidates need a manual review of level, playing time and performance. One snapshot cannot establish development trends.'}

    def acquisition(self,position='',max_salary=100000000,free_only=False):
        ps=[p for p in self.profiles if p['organization_id']!=self.team and p['team_id']!=self.team and not p['draft_eligible'] and (p['free_agent'] or p['league_id']==self.league)]
        if position:ps=[p for p in ps if p['position']==position]
        if free_only:ps=[p for p in ps if p['free_agent']]
        ps=[p for p in ps if p['salary']<=max_salary]
        ps.sort(key=lambda p:(p['score'],p['engine_percentile'] or 0),reverse=True)
        return {'players':ps[:250],'note':'Ranked by rate projection, then game-engine percentile. A free agent salary of $0 means no contract; asking price is unavailable. Trade availability and acceptance are not predicted.'}

    def scenario(self,send,receive,war_value=8000000,war_assumptions=None):
        if len(set(send+receive))!=len(send+receive):raise ValueError('A player can appear only once in a package.')
        outgoing=[self.by_id[i] for i in send];incoming=[self.by_id[i] for i in receive]
        if any(p['organization_id']!=self.team and p['team_id']!=self.team for p in outgoing):raise ValueError('Outgoing players must be in your organization.')
        if any(p['organization_id']==self.team or p['team_id']==self.team for p in incoming):raise ValueError('Incoming players must be outside your organization.')
        years=[]
        for year in range(self.year,self.year+7):
            years.append({'year':year,'payroll_change':sum(p['salaries'].get(year,0) for p in incoming)-sum(p['salaries'].get(year,0) for p in outgoing)})
        flags=[f"{p['name']}: no-trade clause" for p in outgoing+incoming if p['no_trade']]
        flags += [f"{p['name']}: injury flag" for p in incoming if p['injured']]
        flags += [f"{p['name']}: current salary is not exported; this comparison includes only known scheduled salary." for p in outgoing+incoming if not p['salary_known']]
        secondary_delta=sum(p['secondary'] for p in incoming)-sum(p['secondary'] for p in outgoing)
        rows=[]
        for p in outgoing+incoming:
            assumption=(war_assumptions or {}).get(str(p['id']))
            assumed=number(assumption) if assumption is not None else None
            rows.append({'id':p['id'],'name':p['name'],'side':'Outgoing' if p in outgoing else 'Incoming','salary':p['salary'],
                         'salary_known':p['salary_known'],'free_agent':p['free_agent'],
                         'assumed_war':assumed,'scenario_surplus':assumed*war_value-p['salary'] if assumed is not None and p['salary_known'] else None,'score':p['score']})
        return {'players':rows,'years':years,'flags':flags,'secondary_change':secondary_delta,
                'note':'Payroll and roster scenario only; secondary status is not a legal trade validation. Surplus uses YOUR supplied WAR assumption and $/WAR. No trade acceptance or acquisition price is inferred.'}

    def quality(self):
        path=DATA/self.sid/'backtest.json';result=read_json(path)
        if not result or 'tests' not in result:
            result={'tests':{k:backtest(self.hist[k],self.baselines[k],k) for k in ('bat','pit')},
                    'ranges':{k:empirical_range(self.hist[k],self.baselines[k],k) for k in ('bat','pit')}};write_json(path,result)
        return {'manifest':self.manifest,'backtests':result['tests'],'ranges':result['ranges'],'method':VERSION,'baseline_batting':batting(self.base_bat),
                'baseline_pitching':pitching(self.base_pit,self.fip_c),'fip_constant':self.fip_c,
                'limitations':['OPS index is OPS divided by league OPS ×100; it is not OPS+ or wRC+ and has no park adjustment.',
                   'FIP uses the prior MLB season constant, subtracts intentional walks, and includes hit batters.',
                   'Forecasts use 5/4/3 season weights and league-average priors of 300 PA / 200 BF. No aging, ratings, park or injury correction.',
                   'Backtests cover players with prior-year history and minimum later-year exposure; this introduces survivorship selection. MAE is average absolute error, not a confidence interval.',
                   'Historical initial-save data tests the formula but does not validate OOTP future simulation behavior. Track future exported seasons for that.',
                   'No Statcast xwOBA, barrels, SIERA, OAA, or invented minor-league equivalencies.',
                   'No UI reconciliation completed by the app. Compare key players and payroll with OOTP before relying on decisions.']}

def department(sid=None):
    if sid is not None and not re.fullmatch(r'\d{8}T\d{12}Z',sid):raise ValueError('Invalid snapshot identifier.')
    m=current() if sid is None else read_json(DATA/sid/'manifest.json')
    if not m:raise ValueError('Import an export first.')
    with MODEL_LOCK:
        if m['id'] not in CACHE:
            if len(CACHE)>=3:CACHE.pop(next(iter(CACHE)))
            CACHE[m['id']]=Department(m['id'])
        return CACHE[m['id']]
