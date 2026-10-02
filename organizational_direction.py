"""Explain foundational assets and conditional trade exploration from exported evidence."""
from analytics import number,POSITIONS
from scouting import ScoutingReport

CONTEND={'Win now','All in'}
SELL={'Selective sell','Rebuild','Retool'}

def direction_category(age,current,potential,active,controlled,now,next_year,surplus,expiring,locked=False):
    if locked:return 'Protected by GM'
    if age<=28 and current>=7 and controlled:return 'Build-around core'
    if age<=25 and potential>=8 and (not active or current<7):return 'Development cornerstone'
    if active and current>=7 and (now in CONTEND or next_year in CONTEND):return 'Current-window pillar'
    if surplus:return 'Explore a surplus trade'
    if now in SELL and (expiring or age>=30):return 'Explore a window-based trade'
    if expiring and next_year in SELL:return 'Explore before control expires'
    return 'Keep evaluating'

def organizational_direction(office):
    d=office.d;scout=ScoutingReport(office);now=office.b['seasons'].get(str(d.year),'Hold & evaluate');next_year=office.b['seasons'].get(str(d.year+1),'Hold & evaluate');own=[p for p in d.own() if not p['free_agent'] and not p['draft_eligible']];cards={p['id']:office.card(p) for p in own};core=[];trade=[];protected=[]
    healthy=[p for p in own if p['team_id']==d.team and p['active'] and not p['injured'] and not p['on_dl']]
    fa=number(d.leagues[d.league].get('rules_fa_minimum_years'),6)
    for p in own:
        c=cards[p['id']];v=d.ratings['players_value'].get(p['id'],{});oa=number(v.get('oa_rating'));pot=number(v.get('pot_rating'));current=oa if 1<=oa<=10 else c['rating_component'];potential=pot if 1<=pot<=10 else 0;role=('SP' if office.role(p)=='Starters' else 'RP') if p['kind']=='pit' else p['position'];is_active=p['team_id']==d.team and p['active'];scheduled=office.contract_schedule(p);signed_next=any(r['year']>=d.year+1 for r in scheduled);below_fa=number(p.get('service_years'))<fa;controlled=signed_next or below_fa;expiring=bool(p['salary_known'] and not signed_next and not below_fa)
        locks=[l for l in office.state['locks'] if l['player_id']==p['id']];trade_locked=any(l['scope']=='trade' for l in locks)
        backups=[q for q in healthy if q['id']!=p['id'] and q['kind']==p['kind'] and (scout.qualified(q,role) if p['kind']=='bat' else ('SP' if office.role(q)=='Starters' else 'RP')==role) and cards[q['id']]['rating_component']>=max(4.5,c['rating_component']-.5)]
        established=number((p.get('projection') or {}).get('observed_exposure'))>=(300 if p['kind']=='bat' else 200)
        trade_screen_subject=p['team_id']==d.team and (is_active or established)
        surplus=trade_screen_subject and (len(backups)>=2 if p['kind']=='bat' else len(backups)>=6 if role=='SP' else len(backups)>=8)
        category=direction_category(p['age'],current,potential,is_active,controlled,now,next_year,surplus,expiring,trade_locked);facts=[];warnings=[]
        facts.append(f"Age {p['age']}; overall current rating {current:g}/10"+(f" and potential {potential:g}/10." if potential else '; overall potential is not validly exported.'))
        facts.append(c['summary']+' '+c['detail']);facts.extend(c['fit']['notes'])
        facts.append(f"Contract: {c['years_left']} scheduled seasons including this year, through {c['end_year']}." if c['end_year'] else 'No multi-year signed schedule was exported; inspect renewal and team control.')
        if below_fa:facts.append(f"Exported MLB service {number(p.get('service_years')):g} years is below the save’s {fa:g}-year free-agency threshold. Salary schedule length does not equal remaining team control.")
        if signed_next:facts.append('A signed schedule reaches next season; options may make some future salaries conditional.')
        if surplus:facts.append(f"Position-strength screen: {len(backups)} other healthy active MLB options have usable {role} ratings and comparable current-tool preference. They are "+', '.join(q['name'] for q in backups)+'.')
        if p['injured'] or p['on_dl']:warnings.append('Current injury/IL flag: trade interest and recovery need verification. Injury alone is not a sell recommendation.')
        if locks:warnings.append('GM locks: '+', '.join(sorted({l['scope'] for l in locks}))+'. Any deal that conflicts with a lock requires your approval; no lock is removed.')
        if category=='Build-around core':verdict='Build around his current ability and controlled prime years.';condition='Protect this foundation when discussing upgrades. Check extension cost and injury/workload risk rather than treating potential as guaranteed production.'
        elif category=='Development cornerstone':verdict='Protect his upside and create a development path.';condition='This is a future-core recommendation, not a claim that he is MLB-ready. Review current ability, actual-level stats and playing time in MLB Readiness.'
        elif category=='Current-window pillar':verdict='Keep him central to the current contention window.';condition='His current role matters to the plan. Age and contract risk make him a shorter-window pillar rather than an automatic long-term foundation.'
        elif category=='Protected by GM':verdict='Retain trade protection until you approve a change.';condition='The department can discuss opportunity cost, but this player is excluded from the trade-exploration list.'
        elif category=='Explore a surplus trade':verdict=f'Explore a trade: {role} overlap gives us alternatives.';condition='Comparable active options include '+', '.join(q['name'] for q in backups[:3])+'. Seek a return that addresses a greater need; confirm those players can cover his job without opening another hole.';facts.append('Position-only overlap does not prove interchangeability. Other lineup jobs, handedness, defense, options and development must survive a proposed deal.')
        elif category.startswith('Explore'):verdict='Explore offers that match the competitive window.';condition='A return and replacement path must justify the loss. '+('Next season remains a contention year: protect that roster and prefer a replacement with useful control.' if next_year in CONTEND else 'Prioritize future role value and useful control; do not sell solely because the player is older.')
        else:continue
        if category.startswith('Explore'):
            if next_year in CONTEND:condition+=' Protect next year’s contender as well.'
            warnings.append('Trade demand and return are unknown. Salary relief or prospect value is not assumed; salary retention may be needed.')
            if now in CONTEND:condition+=' A win-now deal must improve our overall roster today.'
        item={'player':c,'category':category,'verdict':verdict,'condition':condition,'role':role,'facts':facts,'warnings':warnings,'depth':[{'id':q['id'],'name':q['name'],'current_tools':cards[q['id']]['rating_component']} for q in backups],'current':current,'potential':potential or None,'expiring':expiring,'controlled':controlled,'signed_next':signed_next,'priority':current+potential*.25+c['stat_component']*.5+(2 if category=='Build-around core' else 0)}
        (protected if category=='Protected by GM' else trade if category.startswith('Explore') else core).append(item)
    core.sort(key=lambda x:(x['category']=='Build-around core',x['priority']),reverse=True);trade.sort(key=lambda x:(x['category']=='Explore a surplus trade',x['expiring'],-x['player']['stat_component'],x['player']['salary']),reverse=True)
    return {'now':now,'next':next_year,'core':core,'trade':trade,'protected':protected,'method':['The same player cannot be in both the core and trade lists. Explicit trade locks are retained and shown separately.','Foundation: age 28 or younger, current overall at least 7, and signed future seasons or service below the save’s free-agency threshold. Development cornerstone: age 25 or younger, potential at least 8, and either outside the MLB active roster or still below a current overall rating of 7. These are disclosed screening rules, not a validated aging or trade-value model.','Older/current MLB impact players can be current-window pillars when this year or next year is a contention year. Age alone does not create a trade recommendation.','Position surplus requires at least two other healthy active MLB hitters qualified at the position with comparable current tools; SP/RP require six/eight alternatives; the SP screen preserves five starters plus another comparable active option. Only parent-club players with active status or established MLB history enter the surplus-trade screen. Potential-only and untested minors do not establish surplus. This screen is not a full legal post-trade roster simulation.','Contract/control and now/next-season modes shape conditional trade exploration. Actual game asking prices, salary retention, arbitration outcomes and injury recovery are unverified.','Performance uses the department’s conservative MLB-history assessment alongside current ratings and park fit. An early-season slump or a low salary alone does not trigger a sell recommendation.']}
