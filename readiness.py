"""Current ability, actual level evidence, and a real organizational MLB role."""
import copy
from analytics import number,batting,pitching,combine,BAT_FIELDS,PIT_FIELDS,fip_constant
from frontoffice import Office,percentile
from scouting import ScoutingReport
from storage import connect,records

def clubs(d):return sorted([{'id':tid,'name':d.team_name(tid)} for tid,t in d.teams.items() if t['league_id']==d.league and t['level']==1 and not t.get('allstar_team')],key=lambda t:t['name'])

def team_view(d,team):
    if team not in {t['id'] for t in clubs(d)}:raise ValueError('Choose a supported MLB organization.')
    view=copy.copy(d);view.team=team;view.manifest={**d.manifest,'team_id':team};return view

def organization(d,p):return p['team_id'] if p['team_id'] in {t['id'] for t in clubs(d)} else int(p['organization_id'] or 0)

def tool_score(d,p,potential=False):
    kind=p['kind'];weights={'contact':.3,'power':.35,'eye':.25,'strikeouts':.1} if kind=='bat' else {'stuff':.4,'movement':.3,'control':.3}
    table='players_batting' if kind=='bat' else 'players_pitching';prefix=('batting_ratings_' if kind=='bat' else 'pitching_ratings_')+('talent_' if potential else 'overall_');r=d.ratings[table].get(p['id'],{})
    values=[(number(r.get(prefix+k)),w) for k,w in weights.items()]
    return round(sum(v*w for v,w in values),2) if all(1<=v<=10 for v,w in values) else None

def readiness_verdict(injured,active,current_percentile,qualified,stats):
    if injured:return 'Wait — unavailable','Resolve the injury or injured-list status before planning an MLB role.'
    if not qualified:return 'Wait — role needs work','The intended role is not supported by current position, stamina or repertoire evidence.'
    if current_percentile is None:return 'Needs more evidence','Important current ratings are missing; potential cannot fill that gap.'
    if active:return 'Already in MLB','Review his present role against the alternatives; this is not a new call-up.'
    if current_percentile<25:return 'Keep developing','His current tools trail most MLB players in this role. Future upside does not make him ready today.'
    if not stats or not stats['recent'] or not stats['qualified']:return 'Borderline — prove the role','The current tools warrant attention, but the recent statistical sample is too limited to support a confident promotion.'
    if stats['level']>3:return 'Wait — test a higher level','Production at this level is useful development evidence, but he has not yet shown enough at AA, AAA or MLB.'
    if stats['quality_percentile'] is None or stats['quality_percentile']<35:return 'Borderline — resolve the gap','His current-level production trails many qualified peers. Explain that gap before treating the ratings as proof of readiness.'
    if current_percentile>=50:return 'Ready for an MLB trial','Current tools compare with MLB role players, and recent upper-level production supports a controlled trial with meaningful playing time.'
    return 'Near-ready — needs a clear role','He has usable current tools and supporting performance, but is not an obvious everyday upgrade. A specific matchup or temporary need could justify a trial.'

class ReadinessDesk:
    def __init__(self,d,team=None):
        self.original=d;self.d=team_view(d,int(team or d.team));self.o=Office(self.d);self.scout=ScoutingReport(self.o);self.stat_cache={}

    def cohort(self,p,pos=None):
        role=pos or ('SP' if self.o.role(p)=='Starters' else 'RP') if p['kind']=='pit' else pos or p['position']
        return self.scout.starters(role)[0],role

    def listing(self,q='',minor=True,all_teams=False,offset=0,limit=12):
        d=self.d;ids={c['id'] for c in clubs(d)};pool=[p for p in d.profiles if (organization(d,p) in ids if all_teams else organization(d,p)==d.team) and not p['free_agent'] and not p['draft_eligible']]
        pool=[p for p in pool if q.casefold() in p['name'].casefold() and (not minor or p['team_id']!=organization(d,p) or not p['active'])]
        cohorts={};out=[]
        for p in pool:
            role='SP' if self.o.role(p)=='Starters' else 'RP' if p['kind']=='pit' else 'Hitters'
            if role not in cohorts:cohorts[role]=[tool_score(d,x) for x in self.scout.mlb if x['kind']==p['kind'] and (p['kind']=='bat' or ('SP' if self.o.role(x)=='Starters' else 'RP')==role)]
            current=tool_score(d,p);vals=[v for v in cohorts[role] if v is not None];pct=percentile(vals,current)['percentile'] if current is not None else None
            out.append({'id':p['id'],'name':p['name'],'kind':p['kind'],'position':p['position'],'age':p['age'],'team':p['team'],'organization':d.team_name(organization(d,p)),'organization_id':organization(d,p),'current':current,'potential':tool_score(d,p,True),'current_percentile':pct,'injured':p['injured'] or p['on_dl'],'active':p['active'] and p['team_id']==organization(d,p)})
        out.sort(key=lambda p:(p['injured'],-(p['current_percentile'] if p['current_percentile'] is not None else -1),p['name']))
        return {'players':out[offset:offset+limit],'total':len(out),'clubs':clubs(d),'own_team':self.original.team,'note':'Ratings screen only. Open a review for actual performance, role fit, development and promotion costs. Potential does not set the current-readiness ranking.'}

    def statistics(self,p):
        d=self.d;kind=p['kind'];table='pit_seasons' if kind=='pit' else 'bat_seasons';fields=PIT_FIELDS if kind=='pit' else BAT_FIELDS;exposure='outs' if kind=='pit' else 'pa';threshold=90 if kind=='pit' else 100;out=[]
        levels={t['league_id']:t['level'] for t in d.teams.values() if not t.get('allstar_team')}
        with connect(d.sid) as con:
            rows=records(con,f'select * from {table} where player_id=? and year>=? and year<=? order by year desc,league_id',[p['id'],d.year-3,d.year])
            for r in rows:
                if number(r.get(exposure))<=0:continue
                key=(kind,r['year'],r['league_id'])
                if key not in self.stat_cache:
                    peers=records(con,f'select * from {table} where year=? and league_id=? and {exposure}>0',[r['year'],r['league_id']]);base=combine(peers,fields);constant=fip_constant(base) if kind=='pit' else None
                    metric='fip' if kind=='pit' else 'ops';calc=(lambda row:pitching(row,constant)) if kind=='pit' else batting
                    qualified=[calc(row)[metric] for row in peers if number(row.get(exposure))>=threshold];qualified=[v for v in qualified if v is not None]
                    self.stat_cache[key]=(base,constant,qualified)
                base,constant,peer_values=self.stat_cache[key];metrics=pitching(r,constant) if kind=='pit' else batting(r);league_metrics=pitching(base,constant) if kind=='pit' else batting(base);value=metrics['fip' if kind=='pit' else 'ops'];valid=number(r[exposure])>=threshold
                percent=percentile([-v for v in peer_values],-value) if kind=='pit' and value is not None else percentile(peer_values,value) if value is not None else {'percentile':None,'n':0}
                out.append({**metrics,'year':r['year'],'league_id':r['league_id'],'league':d.leagues.get(r['league_id'],{}).get('abbr',str(r['league_id'])),'level':levels.get(r['league_id'],99),'qualified':valid,'recent':r['year']>=d.year-1,'quality_percentile':percent['percentile'] if valid else None,'comparison_n':percent['n'],'league_metrics':league_metrics,'sample_note':f"Requires {'30 IP' if kind=='pit' else '100 PA'} for a within-league performance rank. Minor-league performance is not an MLB equivalency."})
        out.sort(key=lambda r:(-r['year'],r['level']))
        evidence=next((r for r in out if r['qualified'] and r['recent']),None) or (out[0] if out else None)
        return out,evidence

    def review(self,pid,position=None,hand='vsr'):
        d=self.d;p=d.by_id.get(int(pid))
        if not p or organization(d,p)!=d.team:raise ValueError('Choose a player in this organization.')
        if hand not in ['vsr','vsl']:raise ValueError('Choose a supported handedness comparison.')
        allowed=['SP','RP'] if p['kind']=='pit' else ['C','1B','2B','3B','SS','LF','CF','RF','DH'];role=position or ('SP' if self.o.role(p)=='Starters' else 'RP') if p['kind']=='pit' else position or p['position']
        if role not in allowed:raise ValueError('Choose a role appropriate to the player.')
        skills=self.scout.skill_context(p,role);peers,_=self.scout.starters(role);current=tool_score(d,p);values=[tool_score(d,q) for q in peers];context=percentile([v for v in values if v is not None],current) if current is not None else {'percentile':None,'n':0}
        history,stats=self.statistics(p);qualified=self.scout.qualified(p,role);pitch_count=None;stamina=None
        if p['kind']=='pit':
            r=d.ratings['players_pitching'].get(p['id'],{});stamina=number(r.get('pitching_ratings_misc_stamina'));pitch_count=sum(1 for k,v in r.items() if k.startswith('pitching_ratings_pitches_') and 'talent' not in k and 4<=number(v)<=10)
            if role=='SP':qualified=stamina>=5 and (pitch_count>=3 or (stats and number(stats.get('g'))>0 and number(stats.get('gs'))>=number(stats.get('g'))*.5))
        status,reason=readiness_verdict(p['injured'] or p['on_dl'],p['active'] and p['team_id']==d.team,context['percentile'],qualified,stats)
        card=self.o.card(p);potential=tool_score(d,p,True);potential_peers=[tool_score(d,q,True) for q in d.own() if q['kind']==p['kind'] and q['team_id']!=d.team];potential_peers=[v for v in potential_peers if v is not None];top_upside=potential is not None and len(potential_peers)>=10 and percentile(potential_peers,potential)['percentile']>=90
        roster=self.o.roster(hand);incumbents=[]
        if p['kind']=='pit':
            rows=roster['rotation'] if role=='SP' else roster['bullpen']
            for row in rows:
                if row['player'] and row['player']['id']!=p['id']:incumbents.append({'player':row['player'],'slot':row.get('slot'),'locked':row['locked'] or any(l['scope']=='roster' for l in row['player']['locks'])})
            vacancy=role=='SP' and any(not row['player'] for row in rows)
        else:
            rows=[row for row in roster['lineup'] if row['position']==role];vacancy=not rows
            incumbents=[{'player':row['player'],'slot':row['slot'],'locked':row['locked'] or any(l['scope']=='roster' for l in row['player']['locks'])} for row in rows if row['player']['id']!=p['id']]
        for inc in incumbents:
            q=d.by_id[inc['player']['id']];inc['current']=tool_score(d,q);inc['potential']=tool_score(d,q,True);inc['current_difference']=round((current or 0)-(inc['current'] or 0),2);inc['platoon_difference']=None
            if p['kind']=='bat':
                def platoon(x):
                    r=d.ratings['players_batting'].get(x['id'],{});return sum(number(r.get('batting_ratings_'+hand+'_'+k))*w for k,w in [('contact',.3),('power',.35),('eye',.25),('strikeouts',.1)])
                inc['platoon_difference']=round(platoon(p)-platoon(q),2);inc['defense']=self.scout.fielding(q,role)
        available=[i for i in incumbents if not i['locked']];replacement=min(available or incumbents,key=lambda i:i['current'] if i['current'] is not None else -1) if incumbents else None
        if vacancy:role_read=f"There is an unfilled {role} role in the department’s inferred MLB assignments. Filling that opening does not require removing an established player."
        elif replacement:
            name=replacement['player']['name'];slot=f"rotation spot {replacement['slot']}" if role=='SP' else role;delta=replacement['current_difference']
            role_read=f"The closest replacement question is {name} in {slot}. "+('His current-tool comparison looks stronger, but this does not prove better MLB results.' if delta>=.4 else 'He does not clearly beat that incumbent on current tools; look for injury coverage or a narrower role rather than forcing a promotion.')
            if replacement['locked']:role_read+=' The incumbent is GM-locked. Treat this as a discussion; do not remove him without your approval.'
        else:role_read='He is already in this inferred MLB role, or there is no comparable assignment. Review coverage rather than inventing a displacement.'
        if p['active'] and p['team_id']==d.team:role_read='He is already on this MLB roster. '+role_read
        elif not status.startswith(('Ready','Near-ready')):role_read='This is a role comparison, not a recommendation to call him up yet. '+role_read
        costs=self.o.promotion(p);costs['notes']+=['A call-up and a demotion are separate moves. Confirm options, waivers, injured-list exceptions and roster room in OOTP.']
        if top_upside:costs['notes'].insert(0,'High-upside prospect within this organization: favor regular playing time over a token bench or low-leverage role. Protect development; potential is not a reason to rush him.')
        return {'player':card,'organization':d.team_name(d.team),'organization_id':d.team,'own_team':self.original.team,'status':status,'reason':reason,'role':role,'hand':hand,'current':current,'potential':potential,'current_context':context,'skills':[{**s,'potential':d.ratings['players_batting' if p['kind']=='bat' else 'players_pitching'].get(p['id'],{}).get(('batting_ratings_talent_' if p['kind']=='bat' else 'pitching_ratings_talent_')+s['key'])} for s in skills],'stats':history,'evidence':stats,'top_upside':top_upside,'stamina':stamina,'qualifying_pitches':pitch_count,'qualified':qualified,'replacement':replacement,'incumbents':incumbents,'vacancy':vacancy,'role_read':role_read,'promotion':costs,'contract':self.o.contract_schedule(p),'defense':self.scout.fielding(p,role),'fit':card['fit'],'method':['Readiness is a heuristic review, not a certified promotion or an MLB outcome probability.','Current fixed tools compare with inferred MLB positional regulars or role pitchers. Potential is shown separately and never increases the current-readiness score.','Ready-for-trial screen: at least median current MLB-role tools, qualified role, healthy, recent AA/AAA/MLB sample of 100 PA / 30 IP, and at least the 35th percentile of OPS / inverse FIP within that league and year. These are explicit review thresholds, not validated minor-to-major translations.','Starter role requires stamina at least 5 and either three pitches currently rated at least 4 or recent evidence of primarily starting.','Stats retain year and actual league; FIP uses that league’s run constant. Small samples and stale history reduce the verdict. No minor-league equivalency is fabricated.','MLB assignments are inferred from current healthy players and saved own-team locks, not confirmed exported depth charts. Other organizations use neutral default preferences unless a local blueprint exists.','Service totals are facts from the export; remaining options, move legality, extra control and Super Two timing require game confirmation.','Revisit after a new export changes ratings, health, usage or performance, or when a real playing-time opportunity opens.']}
