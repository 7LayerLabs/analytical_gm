"""Experimental, goal-independent roster/run projection. Never simulates or edits OOTP."""
import collections, copy, hashlib, math, threading
from pathlib import Path
from datetime import date
from analytics import BAT_FIELDS, PIT_FIELDS, POSITIONS, number, fip_constant
from frontoffice import assignment
from storage import DATA, connect, records, read_json, write_json, config

VERSION='roster-runs-1.1'
CACHE={}; LOCK=threading.RLock()

def base_runs(s,multiplier=1):
    h,bb,hp,hr,ibb=[number(s.get(k)) for k in ['h','bb','hp','hr','ibb']]
    tb=h+number(s.get('d'))+2*number(s.get('t'))+3*hr
    a=max(0,h+bb+hp-hr-.5*ibb)
    b=max(0,(1.4*tb-.6*h-3*hr+.1*(bb+hp-ibb)+.9*(number(s.get('sb'))-number(s.get('cs'))-number(s.get('gdp'))))*multiplier)
    c=max(0,number(s.get('ab'))-h+number(s.get('cs'))+number(s.get('gdp')))
    return a*b/(b+c)+hr if b+c else hr

def run_probability(scored,allowed):
    a=max(.01,scored)**1.83;b=max(.01,allowed)**1.83
    return a/(a+b)

def factors(park,side='?'):
    avg='avg_l' if side=='L' else 'avg_r' if side=='R' else 'avg'
    hr='hr_l' if side=='L' else 'hr_r' if side=='R' else 'hr'
    return {k:max(.5,min(1.8,number(park.get(key),1))) for k,key in [('h',avg),('d','d'),('t','t'),('hr',hr)]}

def park_counts(s,park,side='?',inverse=False,home_share=1):
    result=dict(s);f=factors(park,side)
    for k in ['h','d','t','hr']:
        scale=1+home_share*(f[k]-1)
        result[k]=number(s.get(k))*(1/scale if inverse else scale)
    result['h']=min(number(result.get('ab')),max(result['h'],result['d']+result['t']+result['hr']))
    return result

def remaining_injury_games(player,dates,snapshot_date,healthy=False):
    if healthy or not (player.get('injured') or player.get('on_dl')):return 0
    # An unknown recovery is an explicit 30-calendar-day scenario, not inferred certainty.
    days=number(player.get('injury_days')) or 30
    elapsed=[(g-snapshot_date).days for g in dates]
    return sum(0<=day<days for day in elapsed)

class SeasonModel:
    def __init__(self,d):
        if number(d.base_bat.get('pa'))<=0 or number(d.base_pit.get('outs'))<=0:raise ValueError('A completed MLB season with batting and pitching totals is required for a win estimate.')
        self.d=d;self.people={};self.rates={};self.rating_priors={};self.teams={};self.hist={'bat':collections.defaultdict(list),'pit':collections.defaultdict(list)}
        with connect(d.sid) as con:
            self.subleagues=records(con,'select * from sub_leagues where league_id=?',[d.league]);self.divisions=records(con,'select * from divisions where league_id=?',[d.league]);self.records={r['team_id']:r for r in records(con,'select * from team_record')}
            self.games=records(con,'select home_team,away_team,date,played from games where league_id=? and game_type=0 and year(date)=? order by date',[d.league,d.year])
            for kind,table,fields in [('bat','players_career_batting_stats',BAT_FIELDS),('pit','players_career_pitching_stats',PIT_FIELDS)]:
                rows=records(con,f'select * from {table} where league_id=? and year>=? and year<=? and split_id=1 and game_id=0',[d.league,d.year-3,d.year])
                grouped={}
                for row in rows:
                    pid=int(row['player_id']);key=(pid,int(row['year']));park=d.parks.get(d.teams.get(row['team_id'],{}).get('park_id'),{})
                    side={1:'R',2:'L',3:'S'}.get(d.raw.get(pid,{}).get('bats'),'?')
                    neutral=park_counts(row,park,side,True,.5) if kind=='bat' else {**row,'hra':number(row.get('hra'))/(1+.5*(factors(park)['hr']-1))}
                    total=grouped.setdefault(key,{'year':key[1],**{k:0 for k in fields}})
                    for k in fields:total[k]+=number(neutral.get(k))
                for (pid,_),row in grouped.items():self.hist[kind][pid].append(row)
        ids={g[k] for g in self.games for k in ['home_team','away_team']}
        self.clubs={tid:d.teams[tid] for tid in ids if tid in d.teams and d.teams[tid]['league_id']==d.league and not d.teams[tid].get('allstar_team')}
        self.games=[g for g in self.games if g['home_team'] in self.clubs and g['away_team'] in self.clubs]
        self.dates={tid:[g['date'] for g in self.games if not g['played'] and tid in [g['home_team'],g['away_team']]] for tid in self.clubs}
        self.season_games={tid:sum(tid in [g['home_team'],g['away_team']] for g in self.games) for tid in self.clubs}
        for tid in self.clubs:
            record=self.records.get(tid,{});played=self.season_games[tid]-len(self.dates[tid])
            if int(number(record.get('w')))+int(number(record.get('l')))!=played:raise ValueError('Exported standings and completed schedule disagree. Export all files again before projecting the finish.')
        self.snapshot_date=date.fromisoformat(str(d.manifest['game_date'])[:10])
        for pid,p in d.raw.items():
            tid=int(p.get('team_id') or 0);org=int(p.get('organization_id') or tid)
            if org not in self.clubs and tid not in self.clubs:continue
            if p.get('free_agent') or p.get('draft_eligible'):continue
            r=d.roster.get(pid,{});kind='pit' if p.get('position')==1 else 'bat'
            self.people[pid]={'id':pid,'name':p['first_name']+' '+p['last_name'],'team_id':tid,'org':tid if tid in self.clubs else org,'kind':kind,'bats':{1:'R',2:'L',3:'S'}.get(p.get('bats'),'?'),'active':bool(r.get('is_active')),'secondary':bool(r.get('is_on_secondary')),'on_dl':bool(r.get('is_on_dl')),'injured':bool(p.get('injury_is_injured')),'injury_days':p.get('injury_left'),'blocked':bool(r.get('designated_for_assignment') or r.get('is_on_waivers')),'level':d.teams.get(tid,{}).get('level',99)}
        self.baselines={'bat':d.base_bat,'pit':d.base_pit}
        self.exposure={'bat':'pa','pit':'bf'}
        # BaseRuns' advancement multiplier is calibrated to this save's previous MLB run environment.
        b=d.base_bat;a=number(b.get('h'))+number(b.get('bb'))+number(b.get('hp'))-number(b.get('hr'))-.5*number(b.get('ibb'))
        plain=1.4*(number(b.get('h'))+number(b.get('d'))+2*number(b.get('t'))+3*number(b.get('hr')))-.6*number(b.get('h'))-3*number(b.get('hr'))+.1*(number(b.get('bb'))+number(b.get('hp'))-number(b.get('ibb')))+.9*(number(b.get('sb'))-number(b.get('cs'))-number(b.get('gdp')))
        c=number(b.get('ab'))-number(b.get('h'))+number(b.get('cs'))+number(b.get('gdp'));r=number(b.get('r'))-number(b.get('hr'))
        self.multiplier=max(.5,min(2,r*c/plain/(a-r))) if plain and a>r>0 else 1
        self.pa_per_game=number(b.get('pa'))/(number(d.base_pit.get('outs'))/27)
        self.league_ra=number(d.base_pit.get('r'))*27/number(d.base_pit.get('outs'))
        self.league_fip=(13*number(d.base_pit.get('hra'))+3*(number(d.base_pit.get('bb'))-number(d.base_pit.get('iw'))+number(d.base_pit.get('hp')))-2*number(d.base_pit.get('k')))/(number(d.base_pit.get('outs'))/3)+d.fip_c
        self.samples={'bat':[],'pit':[]}
        for p in self.people.values():
            latest=next((r for r in self.hist[p['kind']].get(p['id'],[]) if r['year']==d.base_year),None)
            if latest and number(latest.get(self.exposure[p['kind']]))>=100:self.samples[p['kind']].append((p,latest))
        self.thresholds={}
        for kind in ['bat','pit']:
            values=sorted(self.ability(p) for p in self.people.values() if p['kind']==kind and p['team_id'] in self.clubs and p['active'])
            self.thresholds[kind]=values[int(.25*(len(values)-1))] if values else 5

    def skill(self,p,key):
        if key.startswith('running_'):return number(self.d.ratings['players_batting'].get(p['id'],{}).get(key))
        table='players_batting' if p['kind']=='bat' else 'players_pitching';prefix='batting_ratings_overall_' if p['kind']=='bat' else 'pitching_ratings_overall_'
        return number(self.d.ratings[table].get(p['id'],{}).get(prefix+key))

    def prior(self,p):
        kind=p['kind'];fields=BAT_FIELDS if kind=='bat' else PIT_FIELDS;e=self.exposure[kind];base=self.baselines[kind]
        mapping={'h':'contact','d':'gap','t':'running_ratings_speed','hr':'power','bb':'eye','ab':'eye','k':'strikeouts','sb':'running_ratings_speed','cs':'running_ratings_stealing'} if kind=='bat' else {'k':'stuff','bb':'control','iw':'control','hp':'control','hra':'movement','outs':'stuff'}
        result={k:number(base.get(k))/number(base.get(e)) for k in fields}
        for field,key in mapping.items():
            rating=self.skill(p,key)
            if not 1<=rating<=10:continue
            cachekey=(kind,field,rating)
            if cachekey not in self.rating_priors:
                similar=[r for q,r in self.samples[kind] if abs(self.skill(q,key)-rating)<=1 and 1<=self.skill(q,key)<=10]
                pseudo=1000 if kind=='bat' else 600
                self.rating_priors[cachekey]=(sum(number(r.get(field)) for r in similar)+pseudo*result[field])/(sum(number(r.get(e)) for r in similar)+pseudo)
            result[field]=self.rating_priors[cachekey]
        return result

    def rates_for(self,p):
        if p['id'] in self.rates:return self.rates[p['id']]
        kind=p['kind'];prior=self.prior(p);e=self.exposure[kind];pseudo=300 if kind=='bat' else 200
        weighted={k:pseudo*v for k,v in prior.items()};observed=0
        for r in self.hist[kind].get(p['id'],[]):
            w={0:1.2,1:1,2:.8,3:.6}[self.d.year-r['year']];observed+=number(r.get(e))*w
            for k in weighted:weighted[k]+=w*number(r.get(k))
        result={k:v/(pseudo+observed) for k,v in weighted.items()}
        result['evidence_weight']=observed/(pseudo+observed)
        self.rates[p['id']]=result;return result

    def fielding(self,p,pos):return number(self.d.ratings['players_fielding'].get(p['id'],{}).get('fielding_rating_pos'+str(next(k for k,v in POSITIONS.items() if v==pos)))) if pos!='DH' else 0

    def pitcher_role(self,p):
        stamina=number(self.d.ratings['players_pitching'].get(p['id'],{}).get('pitching_ratings_misc_stamina'));h=self.hist['pit'].get(p['id'],[]);last=max(h,key=lambda r:r['year']) if h else {}
        return 'SP' if stamina>=5 and (not last or number(last.get('gs'))>=.5*number(last.get('g'))) else 'RP'

    def fip(self,r):return (13*r['hra']+3*(r['bb']-r['iw']+r['hp'])-2*r['k'])/max(.15,r['outs']/3)+self.d.fip_c

    def ability(self,p):
        weights={'contact':.3,'power':.35,'eye':.25,'strikeouts':.1} if p['kind']=='bat' else {'stuff':.4,'movement':.3,'control':.3}
        return sum(self.skill(p,k)*w for k,w in weights.items())

    def eligible(self,p,tid):
        if p['org']!=tid or p['blocked']:return False
        if p['team_id']==tid:return p['active'] or p['on_dl'] or p['injured']
        # Plausible depth, not every future prospect. Eligibility/actual promotions remain unverified.
        return (p['secondary'] or p['level'] in [2,3]) and self.ability(p)>=self.thresholds[p['kind']]

    def club(self,tid,healthy=False):
        dates=self.dates[tid];games=max(1,len(dates));allpeople=[p for p in self.people.values() if self.eligible(p,tid)]
        hitters=[p for p in allpeople if p['kind']=='bat'];pitchers=[p for p in allpeople if p['kind']=='pit']
        bat_samples=sorted([self.rates_for(p) for p,_ in self.samples['bat']],key=lambda r:base_runs({k:v*600 for k,v in r.items()},self.multiplier))
        pit_samples=sorted([self.rates_for(p) for p,_ in self.samples['pit']],key=self.fip)
        fallback_bat=bat_samples[int(.2*(len(bat_samples)-1))] if bat_samples else self.prior({'id':-1,'kind':'bat'})
        fallback_pit=pit_samples[int(.8*(len(pit_samples)-1))] if pit_samples else self.prior({'id':-1,'kind':'pit'})
        positions=['C','1B','2B','3B','SS','LF','CF','RF','DH'];slot=self.pa_per_game*games/9;usage=collections.Counter();shares=[];defense={};missing_pa=0;minor_pa=0
        def avail(p):return 1-remaining_injury_games(p,dates,self.snapshot_date,healthy)/games if games else 0
        def bat_quality(p):return base_runs({k:v*600 for k,v in self.rates_for(p).items()},self.multiplier)
        weights=[[((bat_quality(p)+2*self.fielding(p,pos))*avail(p) if (pos=='DH' or self.fielding(p,pos)>=4) and (p['team_id']==tid or avail(p)>0) else -1e6) for p in hitters]+[base_runs({k:v*600 for k,v in fallback_bat.items()},self.multiplier)]*9 for pos in positions]
        selected=assignment(weights);regulars={hitters[i]['id'] for row,i in enumerate(selected) if i<len(hitters) and weights[row][i]>-1e5}
        for ix,pos in enumerate(positions):
            primary=hitters[selected[ix]] if selected[ix]<len(hitters) and weights[ix][selected[ix]]>-1e5 else None
            candidates=([primary] if primary else [])+sorted([p for p in hitters if p is not primary and p['id'] not in regulars and avail(p)>0 and (pos=='DH' or self.fielding(p,pos)>=4)],key=lambda p:(p['team_id']==tid,bat_quality(p)),reverse=True)
            left=slot;field=0
            for p in candidates:
                capacity=max(0,(slot*.85 if p is primary else 450)*avail(p)-usage[p['id']]);take=min(left,capacity)
                if take<=0:continue
                usage[p['id']]+=take;left-=take;rate=self.rates_for(p);shares.append({'id':p['id'],'name':p['name'],'position':pos,'workload':take,'kind':'bat','rates':rate,'bats':p['bats'],'minor':p['team_id']!=tid,'injury_games':remaining_injury_games(p,dates,self.snapshot_date,healthy)})
                field+=self.fielding(p,pos)*take/slot
                if p['team_id']!=tid:minor_pa+=take
                if left<.01:break
            if left>0:shares.append({'id':None,'name':'Replacement-level scenario','position':pos,'workload':left,'kind':'bat','rates':fallback_bat,'bats':'?','minor':False,'injury_games':0});missing_pa+=left;field+=4*left/slot
            defense[pos]=field
        target_ip=games*9;left=target_ip;missing_ip=0;minor_ip=0;used_pitchers=set()
        for role,limit in [('SP',5),('RP',8)]:
            pool=sorted([p for p in pitchers if self.pitcher_role(p)==role and avail(p)>0],key=lambda p:self.fip(self.rates_for(p)))
            for p in pool[:limit]:
                hist=sorted(self.hist['pit'].get(p['id'],[]),key=lambda r:r['year'],reverse=True);recent=number(hist[0].get('outs'))/3 if hist else (150 if role=='SP' else 60)
                capacity=min(190,max(120,recent)) if role=='SP' else min(80,max(45,recent))
                take=min(left,capacity*games/162*avail(p));left-=take
                if take<=0:continue
                used_pitchers.add(p['id'])
                shares.append({'id':p['id'],'name':p['name'],'position':role,'workload':take,'kind':'pit','rates':self.rates_for(p),'minor':p['team_id']!=tid,'injury_games':remaining_injury_games(p,dates,self.snapshot_date,healthy)})
                if p['team_id']!=tid:minor_ip+=take
        for p in sorted([p for p in pitchers if p['id'] not in used_pitchers and avail(p)>0],key=lambda p:(p['team_id']!=tid,self.fip(self.rates_for(p)))):
            take=min(left,(75 if self.pitcher_role(p)=='SP' else 45)*games/162*avail(p));left-=take
            if take<=0:continue
            shares.append({'id':p['id'],'name':p['name'],'position':'Pitching depth','workload':take,'kind':'pit','rates':self.rates_for(p),'minor':p['team_id']!=tid,'injury_games':remaining_injury_games(p,dates,self.snapshot_date,healthy)})
            if p['team_id']!=tid:minor_ip+=take
            if left<.01:break
        if left>0:shares.append({'id':None,'name':'Replacement-level scenario','position':'P','workload':left,'kind':'pit','rates':fallback_pit,'minor':False,'injury_games':0});missing_ip=left
        fip=sum(self.fip(s['rates'])*s['workload'] for s in shares if s['kind']=='pit')/target_ip
        return {'team_id':tid,'name':self.d.team_name(tid),'games':games,'workload_games':games,'shares':shares,'fip':fip,'ra':max(2,self.league_ra+fip-self.league_fip),'defense':defense,'missing_pa':missing_pa,'missing_ip':missing_ip,'minor_pa':minor_pa,'minor_ip':minor_ip,'injuries':[{'name':p['name'],'games':remaining_injury_games(p,dates,self.snapshot_date,healthy),'days_unknown':not number(p.get('injury_days'))} for p in allpeople if remaining_injury_games(p,dates,self.snapshot_date,healthy)>0]}

    def offense(self,club,park):
        counts={k:0 for k in BAT_FIELDS}
        for share in club['shares']:
            if share['kind']!='bat':continue
            c=park_counts({k:share['rates'][k]*share['workload']/club['workload_games'] for k in BAT_FIELDS},park,share['bats'])
            for k in counts:counts[k]+=c[k]
        return max(1,base_runs(counts,self.multiplier))

    def schedule_wins(self,clubs,neutral=False):
        wins=collections.Counter();scored=collections.Counter();allowed=collections.Counter();parkcache={}
        for g in self.games:
            if g['played']:continue
            h,a=g['home_team'],g['away_team'];pid=self.clubs[h].get('park_id') if not neutral else None;park=self.d.parks.get(pid,{})
            for tid in [h,a]:
                if (tid,pid) not in parkcache:parkcache[(tid,pid)]=self.offense(clubs[tid],park)
            rh=parkcache[(h,pid)]*clubs[a]['ra']/self.league_ra;ra=parkcache[(a,pid)]*clubs[h]['ra']/self.league_ra
            probability=run_probability(rh,ra);wins[h]+=probability;wins[a]+=1-probability
            scored[h]+=rh;allowed[h]+=ra;scored[a]+=ra;allowed[a]+=rh
        return wins,scored,allowed

    def build(self):
        if self.d.team not in self.clubs or not self.games:raise ValueError('A complete exported regular-season schedule is required for a season projection.')
        clubs={tid:self.club(tid) for tid in sorted(self.clubs)}
        # Defense coefficient is a disclosed scenario assumption, not learned run value.
        means={pos:sum(c['defense'][pos] for c in clubs.values())/len(clubs) for pos in ['C','1B','2B','3B','SS','LF','CF','RF']}
        for c in clubs.values():
            c['defense_runs']=2*sum(c['defense'][pos]-means[pos] for pos in means)*c['games']/162
            c['ra']=max(2,c['ra']-c['defense_runs']/c['games'])
        wins,rs,ra=self.schedule_wins(clubs)
        rounded={tid:math.floor(wins[tid]) for tid in clubs};extra=sum(not g['played'] for g in self.games)-sum(rounded.values())
        for tid in sorted(clubs,key=lambda tid:-(wins[tid]-rounded[tid]))[:extra]:rounded[tid]+=1
        neutral=self.schedule_wins(clubs,True)[0]
        for tid,c in clubs.items():
            ownrs=self.offense(c,{});c['neutral_probability']=run_probability(ownrs,c['ra']);c['remaining_games']=len(self.dates[tid]);c['played_games']=self.season_games[tid]-c['remaining_games'];c['actual_wins']=int(number(self.records.get(tid,{}).get('w')));c['actual_losses']=int(number(self.records.get(tid,{}).get('l')));c['remaining_expected_wins']=wins[tid];c['expected_wins']=c['actual_wins']+wins[tid];c['wins']=c['actual_wins']+rounded[tid];c['games']=self.season_games[tid];c['losses']=c['games']-c['wins'];c['runs_scored']=round(rs[tid]);c['runs_allowed']=round(ra[tid]);c['park_win_effect']=round(wins[tid]-neutral[tid],1)
            c['division_id']=self.clubs[tid]['division_id'];c['sub_league_id']=self.clubs[tid]['sub_league_id']
            c['unproven_share']=sum(s['workload'] for s in c['shares'] if s['kind']=='bat' and s['rates']['evidence_weight']<.4)/(self.pa_per_game*c['games'])
            spread=round(10+3*c['unproven_share']+min(3,(c['missing_pa']/(self.pa_per_game*c['games'])+c['missing_ip']/(9*c['games']))*10))
            spread=round(spread*math.sqrt(c['remaining_games']/c['games']))
            c['range']={'low':max(c['actual_wins'],c['wins']-spread),'high':min(c['actual_wins']+c['remaining_games'],c['wins']+spread),'label':'Planning range; not a calibrated confidence interval'}
        own=clubs[self.d.team];own['subleague_name']=next((s['name'] for s in self.subleagues if s['sub_league_id']==own['sub_league_id']),'League group');own['division_name']=next((s['name'] for s in self.divisions if s['sub_league_id']==own['sub_league_id'] and s['division_id']==own['division_id']),'Division');division=[c for c in clubs.values() if (c['division_id'],c['sub_league_id'])==(own['division_id'],own['sub_league_id'])];subleague=[c for c in clubs.values() if c['sub_league_id']==own['sub_league_id']]
        for group,key in [(division,'division'),(subleague,'subleague'),(list(clubs.values()),'mlb')]:own[key+'_rank']=1+sum(c['expected_wins']>own['expected_wins']+1e-9 for c in group);own[key+'_size']=len(group)
        healthy=self.club(self.d.team,True);healthy['defense_runs']=2*sum(healthy['defense'][pos]-means[pos] for pos in means)*healthy['games']/162;healthy['ra']=max(2,healthy['ra']-healthy['defense_runs']/healthy['games'])
        healthier=self.schedule_wins({**clubs,self.d.team:healthy})[0][self.d.team];own['known_injury_win_effect']=round(own['remaining_expected_wins']-healthier,1)
        compact=lambda c:{k:v for k,v in c.items() if k not in ['shares','defense']}
        result={'version':VERSION,'year':self.d.year,'snapshot':self.d.sid,'game_date':str(self.d.manifest['game_date']),'opening_day':str(min(g['date'] for g in self.games)),'preseason':not any(g['played'] for g in self.games) and self.snapshot_date<=min(g['date'] for g in self.games),'club':compact(own),'division':sorted([compact(c) for c in division],key=lambda c:-c['expected_wins']),'league':sorted([compact(c) for c in clubs.values()],key=lambda c:-c['expected_wins']),'roster':[{'id':p['id'],'name':p['name']} for p in self.people.values() if p['team_id']==self.d.team],'workloads':[{k:v for k,v in s.items() if k!='rates'} for s in own['shares']] if own['remaining_games'] else [],'method':[
            'Same fixed model for every scheduled MLB club. Goals, identities, finances, potential ratings and GM locks do not change it.',
            'Current MLB season (weight 1.2) and previous three completed MLB seasons (weights 1/.8/.6), plus a 300-PA / 200-BF rating-conditioned prior. Current-rating groups borrow last completed MLB event rates, shrunk toward the league. This cross-sectional translation is experimental, not a temporally validated rating model.',
            'Historical team stints are approximately park-neutralized using half home/half neutral and the currently exported park factors. Historical park changes and exact past road schedules are unavailable. Current schedule applies venue and batting-side hit, double, triple and HR factors to both clubs.',
            'Nine qualified positional regulars assigned globally, with 85% of a position’s PA before known injury absences. Bench and plausible AAA/AA/40-man coverage fill the rest. Five starters and up to eight relievers have bounded history-informed innings, with additional ready depth capped at 75 SP / 45 RP innings. Minor coverage must meet the active-MLB 25th-percentile fixed skill threshold. Unfilled work uses a 20th-percentile MLB offense / 80th-percentile FIP replacement scenario. This is not a confirmed game depth chart or automatic promotion.',
            'BaseRuns estimates offense; its advancement multiplier matches last season’s exported MLB runs. Pitching FIP differences shift league runs allowed. Defense assumes 2 runs per positional-rating point above the modeled league mean per 162 games; this coefficient is a scenario assumption, not calibrated defensive runs. SB/CS enter BaseRuns; first-to-third running, framing, aging and leverage are not fully modeled.',
            'Opponent-specific run matchups use exponent 1.83 and the actual schedule, with complementary game probabilities. No generic home-field boost, future signings/trades, future injuries or playoff odds are invented. The planning range is ±10 wins plus limited-history/coverage allowances; it is not a measured probability interval.',
            'In-season finish estimates keep exported wins and losses already banked, then project only unplayed regular-season games with the current roster, recovery assumptions and remaining venues. Standings must reconcile with completed schedule games. Playing-time tables and run estimates cover the remaining schedule. The model has not been validated against future OOTP seasons. Update exports and compare forecast vs actual results before treating the estimate as reliable.'
        ],'sources':[{'label':'BaseRuns formulation','url':'https://blogs.fangraphs.com/fun-with-baseruns/'},{'label':'BaseRuns use with forecasts','url':'https://library.fangraphs.com/features/baseruns/'},{'label':'Run-based win expectation','url':'https://www.mlb.com/glossary/advanced-stats/pythagorean-winning-percentage'}]}
        return result

def season_projection(d):
    with LOCK:
        key=(d.sid,VERSION,d.team)
        if key not in CACHE:CACHE[key]=SeasonModel(d).build()
        result=copy.deepcopy(CACHE[key]);source=d.manifest.get('source_id') or hashlib.sha256(str(Path(config()['csv_directory']).resolve()).casefold().encode()).hexdigest()[:12];path=DATA/f'preseason-projection-{source}-team{d.team}-league{d.league}-{d.year}.json'
        original=read_json(path)
        if original is None and result['preseason']:
            write_json(path,result);original=copy.deepcopy(result)
        archive_path=DATA/f'projection-archive-{source}-team{d.team}-league{d.league}-{d.year}.json'
        archive=read_json(archive_path,[])
        if original and not any(r.get('snapshot')==original.get('snapshot') and r.get('version')==original.get('version') for r in archive):archive.append(copy.deepcopy(original))
        if not any(r.get('snapshot')==result['snapshot'] and r.get('version')==result.get('version') for r in archive):archive.append(copy.deepcopy(result));write_json(archive_path,archive)
        result['archive']=[{'snapshot':r.get('snapshot'),'version':r.get('version'),'game_date':r.get('game_date'),'wins':r['club']['wins'],'losses':r['club'].get('losses'),'delta_original':r['club']['wins']-original['club']['wins'] if original else None,'range':r['club'].get('range'),'injuries':r['club'].get('injuries',[]),'actual_wins':r['club'].get('actual_wins',0),'actual_losses':r['club'].get('actual_losses',0),'roster':r.get('roster',[])} for r in archive]
        result['delta_original']=result['club']['wins']-original['club']['wins'] if original else None
        result['opening_forecast']=original
        return result
