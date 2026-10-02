"""Pair analytical call-ups with conditional, explicit roster-space moves."""
from analytics import number

def option_review(status):
    used=status.get('options_used');this_year=status.get('options_used_this_year')
    if status.get('must_be_active'):return 'Restricted', 'Export marks must-be-active; do not recommend a routine AAA assignment.'
    if number(status.get('mlb_service_years'))>=5:return 'Consent review', 'Five-plus years of MLB service: confirm assignment consent and veteran rights in OOTP.'
    if this_year is not None and number(this_year)>0:return 'Option already used this year', 'An option is recorded this year; confirm remaining assignment eligibility and any return restrictions.'
    if used is None:return 'Unknown options', 'Option history is missing. Do not assume a waiver-free demotion.'
    if number(used)>=3:return 'Waiver / option review', 'Three or more option years are recorded. Confirm any additional option; otherwise an outright assignment can require waivers and risk losing the player.'
    return 'Conditional option to AAA', f'{int(number(used))} option years recorded; remaining eligibility is not exported. Confirm an option is available before sending him down.'

def roster_moves(office,result):
    d=office.d
    assignments=[(x['player'],x['position'],'Starting lineup') for x in result['lineup']]+[(x['player'],'SP','Starting rotation') for x in result['rotation'] if x['player']]+[(x['player'],'RP','Bullpen') for x in result['bullpen']]+[(x,x['position'],'Bench') for x in result['bench']]
    selected={p['id'] for p,_,_ in assignments};active=[p for p in d.own() if p['team_id']==d.team and p['active'] and not p['on_dl'] and not p['dfa']]
    outgoing=[p for p in active if p['id'] not in selected and not p['injured'] and not any(l['player_id']==p['id'] and l['scope'] in ['roster','lineup','rotation','bullpen'] for l in office.state['locks'])]
    limit=int(number(d.leagues[d.league].get('rules_active_roster_limit'),26));secondary_limit=int(number(d.leagues[d.league].get('rules_secondary_roster_limit'),40));secondary=sum(p['secondary'] for p in d.own());open_active=max(0,limit-len(active));paired=set();moves=[]
    from readiness import ReadinessDesk,tool_score,readiness_verdict
    from frontoffice import percentile
    desk=ReadinessDesk(d)
    for card,role,job in assignments:
        p=d.by_id[card['id']]
        if p['team_id']==d.team and p['active']:continue
        choices=[q for q in outgoing if q['id'] not in paired and q['kind']==p['kind']]
        def preference(q):
            rt=d.roster.get(q['id'],{});restricted=bool(rt.get('must_be_active')) or number(rt.get('mlb_service_years'))>=5 or number(rt.get('options_used'),3)>=3
            return (restricted,office.role(q)!=office.role(p) if p['kind']=='pit' else q['position']!=role,office.card(q)['grade'])
        q=min(choices,key=preference) if choices and open_active==0 else None
        if q:paired.add(q['id'])
        elif open_active:open_active-=1
        peers,_=desk.cohort(p,role);score=tool_score(d,p);values=[tool_score(d,x) for x in peers];context=percentile([v for v in values if v is not None],score) if score is not None else {'percentile':None}
        _,stats=desk.statistics(p);qualified=desk.scout.qualified(p,role)
        if role=='SP':
            rt=d.ratings['players_pitching'].get(p['id'],{});pitches=sum(1 for k,v in rt.items() if k.startswith('pitching_ratings_pitches_') and 'talent' not in k and 4<=number(v)<=10)
            qualified=number(rt.get('pitching_ratings_misc_stamina'))>=5 and (pitches>=3 or (stats and number(stats.get('g'))>0 and number(stats.get('gs'))>=number(stats.get('g'))*.5))
        status,reason=readiness_verdict(p['injured'] or p['on_dl'],False,context['percentile'],qualified,stats)
        supported=status.startswith('Ready') and job!='Bench';checks=[];down=None
        if q:
            route,detail=option_review(d.roster.get(q['id'],{}));supported=supported and route in ['Conditional option to AAA','Option already used this year'];down={'player':office.card(q),'route':route,'detail':detail,'reason':('Regular AAA playing time could support development rather than a reduced MLB role.' if q['age']<=26 else 'He falls outside this proposed MLB roster; AAA would preserve depth only if assignment eligibility permits it.')}
            checks.append('The outgoing player creates active-roster room only after a legal assignment. Confirm coverage against both left- and right-handed pitching.')
        elif len(active)>=limit:checks.append('No unlocked healthy outgoing player of the same type was found. Resolve roster space before this call-up.')
        if not p['secondary']:
            checks.append(f'Adding him to the 40-man is separate from clearing an active spot: {secondary}/{secondary_limit} places exported.')
            if secondary>=secondary_limit:checks.append('40-man space is not demonstrated. An option to AAA does not remove anyone from the 40-man. Review an eligible injured-list exception or a separate removal; DFA/waivers can lose a player. No automatic DFA recommendation.')
            secondary+=1
        if p['kind']=='bat':
            catchers=[x for x,_,_ in assignments if number(d.ratings['players_fielding'].get(x['id'],{}).get('fielding_rating_pos2'))>=4]
            if len(catchers)<2:
                supported=False;checks.insert(0,'The proposed roster has fewer than two usable catchers. Restore backup catcher coverage before making a batting-roster swap.')
        if q is None and len(active)>=limit:supported=False
        if not p['secondary'] and secondary>secondary_limit:supported=False
        checks+=office.promotion(p)['notes']
        if job=='Bench':checks.insert(0,'This selection provides a bench role, not regular starts. Favor continued minor-league playing time for a high-upside prospect unless a concrete MLB usage plan exists.')
        moves.append({'up':card,'role':role,'job':job,'down':down,'readiness':status,'reason':reason,'verdict':'Conditional call-up plan' if supported else 'Do not execute yet: readiness / roster review','checks':checks})
    return {'moves':moves,'active_count':len(active),'active_limit':limit,'remaining_cuts':[office.card(q) for q in outgoing if q['id'] not in paired],'note':'Paired moves are proposals, not transaction approvals. Options used are exported; remaining eligibility, consent, waivers and legal roster exceptions require OOTP confirmation. DFA is never treated as a harmless demotion.'}
