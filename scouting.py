"""Explain a player with fair cohorts and organizational alternatives, not invented outcomes."""
import collections
from analytics import POSITIONS,number
from frontoffice import percentile
from storage import connect,records

def ranked(values,value):
    valid=[number(v) for v in values if v is not None and number(v)>0]
    result=percentile(valid,value)
    result.update(rank_low=1+sum(v>value for v in valid) if valid and value>0 else None,
                  rank_high=sum(v>=value for v in valid) if valid and value>0 else None)
    return result

def standing(context):
    p=context.get('percentile')
    return 'unrated' if p is None else 'exceptional' if p>=95 else 'a major strength' if p>=85 else 'above average' if p>=65 else 'around the middle' if p>=35 else 'below average' if p>=15 else 'a clear weakness'

def describe_rank(c):
    if c['rank_low'] is None:return 'No valid rating comparison is available.'
    rank=str(c['rank_low']) if c['rank_low']==c['rank_high'] else f"{c['rank_low']}–{c['rank_high']} (tied)"
    return f"Rank {rank} of {c['n']}; midpoint percentile {c['percentile']:.1f}."

class ScoutingReport:
    def __init__(self,office):
        self.o=office;self.d=office.d;self._cohorts={};self._scores={}
        with connect(self.d.sid) as con:
            # Fielding exports have split_id, but no game_id. Sum only total split, by player/position.
            rs=records(con,'select player_id,position,sum(gs) starts from players_career_fielding_stats where league_id=? and year=? and split_id=1 group by player_id,position',[self.d.league,self.d.base_year])
        self.starts={(r['player_id'],r['position']):number(r['starts']) for r in rs}
        self.mlb=[p for p in self.d.profiles if p['league_id']==self.d.league and self.d.teams.get(p['team_id'],{}).get('league_id')==self.d.league]

    def qualified(self,p,pos):
        if p['kind']=='pit':return pos=='RP' or pos=='SP' and self.o.role(p)=='Starters'
        if pos=='DH':return True
        code=next((k for k,v in POSITIONS.items() if v==pos),None)
        return code is not None and number(self.d.ratings['players_fielding'].get(p['id'],{}).get(f'fielding_rating_pos{code}'))>=4

    def starters(self,pos):
        if pos in self._cohorts:return self._cohorts[pos]
        if pos in ['SP','RP']:
            role='Starters' if pos=='SP' else 'Relievers';ps=[p for p in self.mlb if p['kind']=='pit' and self.o.role(p)==role]
            method='Currently assigned MLB pitchers, grouped by stamina and most recent MLB starting usage. Role is inferred.'
        else:
            code=next(k for k,v in POSITIONS.items() if v==pos);teams=collections.defaultdict(list)
            for p in self.mlb:
                if p['kind']=='bat' and self.qualified(p,pos) and (p['active'] or p['on_dl'] or self.starts.get((p['id'],code),0)>=35):teams[p['team_id']].append(p)
            ps=[]
            for group in teams.values():
                # Usage comes first. Do not pick comparison players by the skill being evaluated.
                ps.append(max(group,key=lambda p:(self.starts.get((p['id'],code),0),p['position']==pos,p['active'],p['engine_value'])))
            method=f"One inferred regular {pos} per current MLB team with qualified candidates. Uses {self.d.base_year} starts at that position, then listed position, active status and engine value. Injured regulars remain in the benchmark. This is not an exported depth chart."
            if pos=='DH':method=f"One inferred DH per team using listed DH position, then active status and engine value; historical DH starts are unavailable."
        self._cohorts[pos]=(ps,method);return ps,method

    def rating(self,p,key):
        table='players_batting' if p['kind']=='bat' else 'players_pitching';prefix='batting_ratings_overall_' if p['kind']=='bat' else 'pitching_ratings_overall_'
        value=self.d.ratings[table].get(p['id'],{}).get(prefix+key)
        return number(value) if value is not None and 0<number(value)<=10 else None

    def skill_context(self,p,pos):
        starters,method=self.starters(pos);all_players=[x for x in self.mlb if x['kind']==p['kind']];out=[]
        for label,key in self.o.skill_specs(p['kind']):
            value=self.rating(p,key);a=ranked([self.rating(q,key) for q in starters],value or 0);b=ranked([self.rating(q,key) for q in all_players],value or 0)
            if value is None:a['percentile']=b['percentile']=None
            group=f'MLB {"starting "+pos if pos not in ["SP","RP"] else "starters" if pos=="SP" else "relievers"}'
            explanation=f"{label} is {standing(a)} among {group}, and {standing(b)} among all MLB {'hitters' if p['kind']=='bat' else 'pitchers'}." if value is not None else 'The current rating is missing or outside the configured 1–10 scale.'
            if key=='power' and a['rank_high'] is not None and a['rank_high']<=10 and a['n']>=20:explanation=f"A top-10 power rating among starting {pos}s, including the entire tied group. This describes rated power, not a home-run leaderboard. "+explanation
            out.append({'label':label,'key':key,'value':value,'position':a,'league':b,'position_label':group,'explanation':explanation,'position_detail':describe_rank(a),'league_detail':describe_rank(b),'method':method})
        return out

    def fielding(self,p,pos):
        if p['kind']=='pit':return number(self.d.ratings['players_pitching'].get(p['id'],{}).get('pitching_ratings_misc_stamina'))
        if pos=='DH':return 0
        code=next(k for k,v in POSITIONS.items() if v==pos)
        return number(self.d.ratings['players_fielding'].get(p['id'],{}).get(f'fielding_rating_pos{code}'))

    def fit(self,p,pos):
        ps,_=self.starters(pos);rating=self.o.card(p)['rating_component'];comparison=percentile([self.o.card(q)['rating_component'] for q in ps],rating)
        if p['kind']=='pit':return self.o.card(p)['grade']
        return round(.6*self.o.card(p)['grade']+.3*self.fielding(p,pos)+.1*(comparison['percentile'] or 0)/10,2)

    def readiness(self,p,pos):
        if p['injured'] or p['on_dl']:return ('Unavailable','Injury or injured-list flag; verify recovery before assigning a role.',3)
        if p['active'] and p['team_id']==self.d.team:return ('Ready now','Healthy and currently active on the major-league roster; still verify game eligibility.',0)
        cohort,_=self.starters(pos);ability=self.o.card(p)['rating_component'];vals=sorted(self.o.card(q)['rating_component'] for q in cohort)
        floor=vals[int((len(vals)-1)*.25)] if vals else 5
        if ability>=floor:
            return ('Possible promotion','Current skill preferences compare credibly with the MLB role. Review actual level, performance, playing time and roster/control costs before promoting.',1)
        return ('Future option','Current skill preferences trail most established players in this role. Potential alone does not establish immediate readiness.',2)

    def best_position(self,p):
        if p['kind']=='pit':return 'SP' if self.o.role(p)=='Starters' else 'RP'
        options=[pos for pos in ['C','1B','2B','3B','SS','LF','CF','RF','DH'] if self.qualified(p,pos)]
        return max(options,key=lambda pos:(self.fit(p,pos),pos==p['position'])) if options else 'DH'

    def alternatives(self,p,pos):
        roster=self.o.roster();assignments={x['player']['id']:x['position'] for x in roster['lineup']}
        pitching_assigned={x['player']['id'] for x in roster['rotation'] if x['player']}
        out=[]
        for q in self.d.own():
            if q['id']==p['id'] or q['kind']!=p['kind'] or not self.qualified(q,pos):continue
            readiness,reason,rank=self.readiness(q,pos);locked_elsewhere=any(l['scope']=='lineup' and l['position'] and l['position']!=pos or l['scope']=='rotation' and pos=='RP' or l['scope']=='bullpen' and pos=='SP' for l in self.o.card(q)['locks'])
            displaced=assignments.get(q['id']) not in [None,pos] if p['kind']=='bat' else q['id'] in pitching_assigned
            costs=[]
            if displaced:costs.append(f"Already assigned at {assignments.get(q['id'],'another rotation spot')}; using him here creates a coverage question elsewhere.")
            if not q['active']:costs.extend(self.o.promotion(q)['notes'][:2])
            if locked_elsewhere:costs.append('A saved GM lock places him elsewhere; changing it requires your approval.')
            out.append({'player':self.o.card(q),'readiness':readiness,'readiness_reason':reason,'role_fit':self.fit(q,pos),'defense':self.fielding(q,pos),'costs':costs,'blocked':locked_elsewhere,'displaces':displaced,'readiness_rank':rank})
        out.sort(key=lambda x:(x['blocked'],x['readiness_rank']==3,x['displaces'],x['readiness_rank'],-x['role_fit']))
        return out

    def assessment(self,p,pos):
        allowed=['SP','RP'] if p['kind']=='pit' else ['C','1B','2B','3B','SS','LF','CF','RF','DH']
        if pos not in allowed:raise ValueError('Choose an intended role appropriate to the player.')
        card=self.o.card(p);skills=self.skill_context(p,pos);main=[x for x in skills if x['key'] not in ['babip','pbabip','hra']];best=max(main,key=lambda x:x['league']['percentile'] if x['league']['percentile'] is not None else -1);weak=min(main,key=lambda x:x['league']['percentile'] if x['league']['percentile'] is not None else 101)
        projection=p['projection'];exposure=int(number(projection.get('observed_exposure')));unit='plate appearances' if p['kind']=='bat' else 'batters faced';ready,ready_reason,_=self.readiness(p,pos);best_fit=self.best_position(p);alternatives=self.alternatives(p,pos);practical=[x for x in alternatives if not x['blocked'] and x['readiness_rank']<2];alternative=(practical or alternatives or [None])[0]
        opening=card['summary'].rstrip('.')
        verdict=opening+f", led by {best['label'].lower()}." if p['kind']=='bat' else opening+'.'
        paragraphs=[f"{best['label']} gives this profile its clearest strength. "+best['explanation']]
        if exposure:paragraphs.append(f"The completed MLB sample covers {exposure:,} {unit} across the last three seasons. "+('That is still limited evidence: the forecast gives the league baseline a meaningful share of the result, rather than assuming the early performance will repeat.' if projection.get('evidence')!='Established' else 'There is enough history to judge a sustained track record, while the league prior still tempers the forecast.'))
        else:paragraphs.append('There is no completed MLB sample to support a personal rate forecast. The statistical line is a league prior; his actual level, ratings and development history need to do the explanatory work.')
        if weak['league']['percentile'] is not None and weak['league']['percentile']<35:paragraphs.append(f"{weak['label']} is the main caution: {weak['explanation']} A role that uses his strengths should also account for this limitation.")
        role='Starting pitcher' if pos=='SP' else 'Relief role' if pos=='RP' else 'Everyday '+pos+' candidate' if ready=='Ready now' and card['grade']>=5.5 else 'Matchup / depth '+pos+' candidate'
        if ready!='Ready now':role=ready+' · '+('starter' if pos=='SP' else 'relief' if pos=='RP' else pos)
        locks=[l for l in card['locks'] if l['scope'] in ['lineup','rotation','bullpen','roster']]
        qualified=self.qualified(p,pos)
        if not qualified:role='Position fit needs review'
        conclusion=f"Use {p['name']} as a {pos} option: his current profile supports this role, subject to availability and a complete roster comparison."
        if not qualified:conclusion=f"Do not treat {pos} as an established fit yet. His exported position qualification falls below the department threshold."
        elif ready=='Unavailable':conclusion=f"Keep {p['name']}'s future role in view, but resolve his injury status before planning to use him today."
        elif alternative:
            q=alternative['player'];delta=self.fit(p,pos)-alternative['role_fit']
            if locks:conclusion=f"Keep {p['name']} in the role required by your lock. {q['name']} is a comparison, not permission to remove him."
            elif delta>=.25 and ready=='Ready now':conclusion=f"Prefer {p['name']} for {pos} under the current plan. {q['name']} is the strongest practical internal comparison, but trails the combined offensive/position-fit preference."
            elif delta<=-.25 and alternative['readiness']=='Ready now':conclusion=f"Consider {q['name']} first for {pos}; his combined current skill and position fit is stronger. Keep {p['name']}'s development and best-fit role in view."
            else:conclusion=f"There is no decisive preference gap between {p['name']} and {q['name']} for {pos}. Let the matchup, defensive need and roster cost decide rather than overstating a small grade difference."
        if locks:conclusion+=' Standing GM locks remain binding until you approve a change.'
        current_text=f"His strongest current skill is {best['label'].lower()}. "+best['explanation']+f" {weak['label']} is {standing(weak['league'])} in the wider MLB comparison."
        table='players_batting' if p['kind']=='bat' else 'players_pitching';prefix='batting_ratings_talent_' if p['kind']=='bat' else 'pitching_ratings_talent_';r=self.d.ratings[table].get(p['id'],{});growth=[]
        for label,key in self.o.skill_specs(p['kind']):
            now=self.rating(p,key);potential=number(r.get(prefix+key))
            if now is not None and potential>now:growth.append((potential-now,label,now,potential))
        growth.sort(reverse=True)
        future='The export sees the clearest remaining room in '+', '.join(f'{label.lower()} ({a:g} current / {b:g} potential)' for _,label,a,b in growth[:2])+'. Potential describes an upside rating, not a promise that he will reach it.' if growth else 'The main skill ratings show little separation between current ability and potential. Maintaining production and covering the role matter more than assuming a large tools jump; future ratings can still change.'
        fit_text=f"Your intended use is {pos}; the department's positional preference is {best_fit}. "+('Those agree, so we can concentrate on the lineup matchup and coverage behind him. ' if pos==best_fit else 'That difference deserves a discussion: moving him can improve one role while creating a defensive or roster tradeoff elsewhere. ')+card['fit']['notes'][0]
        return {'subject_defense':self.fielding(p,pos),'verdict':verdict,'paragraphs':paragraphs,'intended_position':pos,'best_fit':best_fit,'role':role,'readiness':ready,'readiness_reason':ready_reason,'recommendation':conclusion,'current':current_text,'future':future,'fit':fit_text,'skills':skills,'alternative':alternative,'alternatives':alternatives[:30],'qualified':qualified,'locked':bool(locks),'why':f"Uses current ratings, conservative MLB history, position qualification and organizational readiness. {self.d.base_year} recorded usage defines inferred positional benchmarks; it is not a confirmed current depth chart.",'what_changes':['A new export changes health, current ratings, usage or recorded performance.','The intended position, handedness matchup or team direction changes.','An alternative becomes ready, or roster/contract costs alter the practical choice.','You approve a change to a saved GM lock.'],'grade_note':'A preference score, not predicted wins. The existing 65% ratings / 35% MLB-rate / bounded park formula stays unchanged.'}
