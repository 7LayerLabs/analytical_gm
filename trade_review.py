"""Roster-based trade verdicts with explicit current/future costs and uncertainty."""
import copy
from analytics import number,POSITIONS

def trade_verdict(core_lost,comparable_core,now_gain,recovery_gain,mode,missing=False):
    if missing:return 'Needs more evidence'
    if core_lost and not comparable_core:return 'Decline this trade'
    if now_gain<-.15 or recovery_gain<-.15:return 'Decline this trade'
    if now_gain>=.15 and recovery_gain>=-.05:return 'Worth pursuing'
    return 'Revise the package'

def analyze_trade(office,send,receive,mode):
    d=office.d
    if not send or not receive:raise ValueError('Choose at least one outgoing and one incoming player.')
    outgoing=[d.by_id[i] for i in send];incoming=[d.by_id[i] for i in receive]
    def value(p,key):
        v=number(d.ratings['players_value'].get(p['id'],{}).get(key));return v if 1<=v<=10 else None
    def core(p):return p['age']<=28 and ((value(p,'oa_rating') or 0)>=7 or (value(p,'pot_rating') or 0)>=8)
    foundations=[p for p in outgoing if core(p)]
    comparable=len([q for q in incoming if core(q)])>=len(foundations) and all(any(core(q) and (value(q,'oa_rating') or 0)>=(value(p,'oa_rating') or 0)-1 and (value(q,'pot_rating') or 0)>=(value(p,'pot_rating') or 0)-1 for q in incoming) for p in foundations)
    from frontoffice import Office
    def changed(healthy=False):
        view=copy.copy(d);view.profiles=copy.deepcopy(d.profiles);view.by_id={p['id']:p for p in view.profiles}
        for pid in send:
            p=view.by_id[pid];p.update(team_id=0,organization_id=0,active=False)
        for pid in receive:
            p=view.by_id[pid];p.update(team_id=d.team,organization_id=d.team,team=d.team_name(d.team),league_id=d.league,active=True,free_agent=False)
        if healthy:
            for pid in receive:view.by_id[pid].update(injured=False,on_dl=False)
        return Office(view)
    after=changed();before_healthy_view=copy.copy(d);before_healthy_view.profiles=copy.deepcopy(d.profiles);before_healthy_view.by_id={p['id']:p for p in before_healthy_view.profiles}
    for pid in send:
        original=d.by_id[pid];before_healthy_view.by_id[pid].update(injured=False,on_dl=False)
        if original['team_id']==d.team and (original['injured'] or original['on_dl']):before_healthy_view.by_id[pid]['active']=True
    recovery_before=Office(before_healthy_view);recovery_after=changed(True)
    def assignments(o,hand):
        r=o.roster(hand);slots={x['position']:x['player'] for x in r['lineup']}
        slots.update({f'SP {x["slot"]}':x['player'] for x in r['rotation']})
        slots.update({f'RP {i+1}':x['player'] for i,x in enumerate(r['bullpen'])})
        slots.update({f'Bench {i+1}':p for i,p in enumerate(r['bench'])})
        return slots,r
    def compare(a,b,hand):
        old,br=assignments(a,hand);new,ar=assignments(b,hand);changes=[]
        for role in dict.fromkeys([*old,*new]):
            x,y=old.get(role),new.get(role)
            if (x or {}).get('id')!=(y or {}).get('id'):changes.append({'role':role,'before':x,'after':y})
        def strength(slots):
            # Fixed 26 places; empty places count zero, so dropping coverage cannot improve the mean.
            return sum((p['grade'] if p else 0) for p in slots.values())/26
        return round(strength(new)-strength(old),2),changes,ar
    comparisons=[];current=[];recovered=[];jobs={p['id']:[] for p in incoming};warnings=[]
    for hand in ['vsr','vsl']:
        delta,changes,r=compare(office,after,hand);future,_,_=compare(recovery_before,recovery_after,hand);current.append(delta);recovered.append(future)
        comparisons.append({'hand':hand,'changes':changes,'current_change':delta,'recovery_change':future})
        for row in changes:
            if row['after'] and row['after']['id'] in jobs:jobs[row['after']['id']].append(('vs RHP' if hand=='vsr' else 'vs LHP')+': '+row['role'])
        warnings.extend(r['warnings'])
    now_gain=round(sum(current)/2,2);recovery_gain=round(sum(recovered)/2,2);missing=any(value(p,'oa_rating') is None for p in outgoing+incoming)
    verdict=trade_verdict(bool(foundations),comparable,now_gain,recovery_gain,mode,missing)
    if verdict=='Decline this trade' and foundations and not comparable:
        lead='Keep '+', '.join(p['name'] for p in foundations)+'. The return does not provide a comparable young foundation, and extra bodies do not compensate for that loss.'
    elif verdict=='Decline this trade':lead='Keep the current roster. The proposed assignments lose more current role quality than they add, especially after the outgoing players recover.'
    elif verdict=='Worth pursuing':lead='The package improves the inferred roster enough to investigate. Confirm the asking package, eligibility and future salary before agreeing.'
    elif verdict=='Needs more evidence':lead='Important overall ratings are missing. We can compare roles, but should not make a confident talent-cost judgment yet.'
    else:lead='The current package does not establish a strong enough roster improvement. Ask for a more useful role upgrade or reduce the talent we give up.'
    reasons=[]
    for p in foundations:
        c=office.card(p);reasons.append(f"{p['name']} is {p['age']}, with current overall {value(p,'oa_rating') or 'unknown'}/10 and potential {value(p,'pot_rating') or 'unknown'}/10"+(f", signed through {c['end_year']}." if c['end_year'] else '.'))
    reasons.append('The immediate roster offers '+('a meaningful preference improvement.' if now_gain>=.15 else 'some help in current roles, but only a modest preference improvement.' if now_gain>.05 else 'a weaker set of selected roles.' if now_gain<-.05 else 'little overall preference improvement.')+' This compares assigned jobs, not the number of players in the package.')
    for p in foundations:
        s=p.get('recorded',{})
        if p['kind']=='bat' and p.get('recorded_year')==d.year and number(s.get('pa'))>0:
            reasons.append(f"This season, {p['name']} has a {number(s.get('obp')):.3f} OBP and {number(s.get('ops')):.3f} OPS over {number(s.get('pa')):g} MLB plate appearances. Those observed results are separate from the conservative forecast and are not park-neutral.")
    injured=[p['name'] for p in outgoing if p['injured'] or p['on_dl']]
    if injured:reasons.append('Do not confuse temporary coverage for '+', '.join(injured)+' with a permanent upgrade. After restoring the package players to health, the roster comparison is '+('weaker.' if recovery_gain<-.05 else 'roughly unchanged.' if recovery_gain<=.05 else 'stronger.')+' This tests the roster consequence, not when an injury will heal.')
    if mode in ['Win now','All in'] and office.b['seasons'].get(str(d.year+1)) in ['Win now','All in']:reasons.append('We intend to contend this year and next. A short-term injury patch must justify its cost to next year’s core.')
    people=[]
    for side,ps in [('Outgoing',outgoing),('Incoming',incoming)]:
        for p in ps:
            c=office.card(p);r=d.ratings['players_batting' if p['kind']=='bat' else 'players_pitching'].get(p['id'],{});prefix='batting_ratings_overall_' if p['kind']=='bat' else 'pitching_ratings_overall_';skills=['contact','gap','power','eye','strikeouts'] if p['kind']=='bat' else ['stuff','movement','control']
            people.append({'player':c,'side':side,'current':value(p,'oa_rating'),'potential':value(p,'pot_rating'),'tools':{k:r.get(prefix+k) for k in skills},'jobs':jobs.get(p['id'],[]),'observed':p.get('recorded',{}),'observed_year':p.get('recorded_year'),'assessment':c['summary']+' '+c['detail'],'control':f"Signed schedule through {c['end_year']}; {c['years_left']} seasons including this year." if c['years_left']>1 else f"Only this year’s signed salary is shown. Exported MLB service: {number(p.get('service_years')):g} years; below the save’s free-agency threshold does not mean a free agent after this season.",'park':c['fit']['notes']})
    financial=[]
    for year in range(d.year,d.year+7):
        amounts={p['id']:next((r['salary'] for r in office.contract_schedule(p) if r['year']==year),None) for p in outgoing+incoming}
        unknown=[p['name'] for p in outgoing+incoming if amounts[p['id']] is None]
        financial.append({'year':year,'known_change':sum(amounts[p['id']] or 0 for p in incoming)-sum(amounts[p['id']] or 0 for p in outgoing),'unknown':unknown,'complete':not unknown})
    from owner_goals import owner_context
    impacts=[]
    for g in owner_context(office)['goals']:
        if g['category']=='Playoffs':impacts.append({'goal':g['title'],'read':'The immediate assignment improvement does not establish a meaningful playoff gain or justify the core talent cost.' if foundations and not comparable else 'Assess the changed MLB roles against the talent cost. This review does not calculate playoff odds.'})
        elif g['category']=='Position upgrade':
            pos=g['position'];changed_roles=[x for c in comparisons for x in c['changes'] if x['role']==pos]
            impacts.append({'goal':g['title'],'read':'Changes the inferred '+pos+' assignment; compare the two players before calling this an upgrade.' if changed_roles else 'This package does not change the inferred '+pos+' starter; it does not demonstrate progress toward this goal.'})
        elif g['category']=='Championship window':impacts.append({'goal':g['title'],'read':'Giving up a young foundation without a comparable return conflicts with the longer contention path.' if foundations and not comparable else 'Review controlled role value and future payroll, not just today’s salary difference.'})
        elif g['category'] in ['Popularity','Chemistry','Fan interest']:impacts.append({'goal':g['title'],'read':'Not established by this review. Verify popularity/clubhouse information in OOTP; a trade does not guarantee an increase.'})
    uncertain=[x for x in impacts if x['read'].startswith('Not established')]
    if uncertain:
        impacts=[x for x in impacts if x not in uncertain]+[{'goal':'; '.join(x['goal'] for x in uncertain),'read':'None of these outcomes is demonstrated by this package. Check national popularity and clubhouse reports; any fan-interest response remains uncertain.'}]
    active_now=sum(p['team_id']==d.team and p['active'] and not p['on_dl'] and not p['dfa'] for p in d.own());active_removed=sum(p['active'] and not p['on_dl'] and not p['dfa'] for p in outgoing);healthy_added=sum(not p['injured'] and not p['on_dl'] for p in incoming);active_after=active_now-active_removed+healthy_added;limit=int(number(d.leagues[d.league].get('rules_active_roster_limit'),26))
    warnings.insert(0,f'Active-roster scenario: {active_now} now, {active_removed} outgoing active players, {healthy_added} healthy incoming MLB assignments = {active_after} before other moves. '+(f'Review {active_after-limit} additional assignments to reach the {limit}-player limit; trading an injured-list player does not clear an active spot.' if active_after>limit else 'Confirm the actual game limit and eligibility.'))
    checks=list(dict.fromkeys(warnings))+['The post-trade roster assumes incoming players can be assigned to MLB; verify active and 40-man room, options, waivers and any no-trade restrictions.','Renewal/arbitration, options, retained salary and proration can change the real cost. Missing future salaries are unknown, not zero.']
    return {'verdict':verdict,'lead':lead,'reasons':reasons,'comparisons':comparisons,'people':people,'financial':financial,'owner_impact':impacts,'checks':checks,'method':'Heuristic review: compare actual inferred assignments against both pitcher hands, show current and recovery scenarios, and flag young-core losses without a comparable overall/potential return. Core screening uses age <=28 and current >=7 or potential >=8. Decline when mean roster grade falls more than 0.15; pursue only when it rises at least 0.15 without a recovery loss below -0.05. These thresholds are disclosed preferences, not a calibrated trade-value model. Grades are never summed across package players to claim fair trade value.'}
