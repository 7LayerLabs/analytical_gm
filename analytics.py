"""Transparent baseball calculations. No model performs arithmetic."""
import math

VERSION = '2026.1'
POSITIONS = {1:'P',2:'C',3:'1B',4:'2B',5:'3B',6:'SS',7:'LF',8:'CF',9:'RF',10:'DH'}
BAT_FIELDS = 'ab h k pa g gs d t hr r rbi sb cs bb ibb gdp sh sf hp ci war ubr'.split()
PIT_FIELDS = 'outs ha k bf bb er r hra hp iw g gs w l s hld war ra9war'.split()

def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default

def ratio(a,b):
    return a/b if b else None

def rounded(value, digits=3):
    return round(value,digits) if value is not None and math.isfinite(value) else None

def batting(s):
    n = {k:number(s.get(k)) for k in BAT_FIELDS}
    singles=n['h']-n['d']-n['t']-n['hr']
    tb=singles+2*n['d']+3*n['t']+4*n['hr']
    avg=ratio(n['h'],n['ab']); obp=ratio(n['h']+n['bb']+n['hp'],n['ab']+n['bb']+n['hp']+n['sf'])
    slg=ratio(tb,n['ab'])
    return {**n,'avg':rounded(avg),'obp':rounded(obp),'slg':rounded(slg),
            'ops':rounded(obp+slg) if obp is not None and slg is not None else None,
            'iso':rounded(slg-avg) if slg is not None and avg is not None else None,
            'bb_pct':rounded(ratio(n['bb'],n['pa'])),'k_pct':rounded(ratio(n['k'],n['pa'])),
            'babip':rounded(ratio(n['h']-n['hr'],n['ab']-n['k']-n['hr']+n['sf'])),
            'sb_pct':rounded(ratio(n['sb'],n['sb']+n['cs']))}

def pitching(s,constant=3.2):
    n={k:number(s.get(k)) for k in PIT_FIELDS}; ip=n['outs']/3
    fip=ratio(13*n['hra']+3*(n['bb']-n['iw']+n['hp'])-2*n['k'],ip)
    return {**n,'ip':rounded(ip,2),'ip_display':f"{int(n['outs'])//3}.{int(n['outs'])%3}",
            'era':rounded(ratio(n['er']*9,ip),2),'whip':rounded(ratio(n['bb']+n['ha'],ip),2),
            'fip':rounded(fip+constant,2) if fip is not None else None,
            'k_pct':rounded(ratio(n['k'],n['bf'])),'bb_pct':rounded(ratio(n['bb'],n['bf'])),
            'k_bb_pct':rounded(ratio(n['k']-n['bb'],n['bf'])),
            'hr9':rounded(ratio(n['hra']*9,ip),2)}

def combine(rows,fields):
    return {k:sum(number(r.get(k)) for r in rows) for k in fields}

def fip_constant(s):
    ip=number(s.get('outs'))/3
    return (number(s.get('er'))*9-(13*number(s.get('hra'))+3*(number(s.get('bb'))-number(s.get('iw'))+number(s.get('hp')))-2*number(s.get('k'))))/ip if ip else 3.2

def projection(history, target_year, league, kind, workload=None):
    """5/4/3 recency weights with 300 PA / 200 BF league-average prior.
    No ratings, future seasons, arbitrary minor-league translations, or park corrections.
    Rates are exposure-weighted; workload is a separate scenario.
    """
    fields=BAT_FIELDS if kind=='bat' else PIT_FIELDS
    exposure='pa' if kind=='bat' else 'bf'; prior=300 if kind=='bat' else 200
    rows=[r for r in history if target_year-3<=int(r['year'])<target_year]
    weighted={k:0.0 for k in fields}; observed=0
    for r in rows:
        weight={1:5,2:4,3:3}[target_year-int(r['year'])]/5
        observed+=number(r.get(exposure))
        for k in fields: weighted[k]+=number(r.get(k))*weight
    le=number(league.get(exposure)); denom=weighted[exposure]+prior
    rates={k:(weighted[k]+prior*number(league.get(k))/le)/denom if le else 0 for k in fields}
    recent=sorted(rows,key=lambda r:r['year'],reverse=True)
    if kind=='bat':
        pa=workload if workload is not None else min(650,max(100,number(recent[0].get('pa')) if recent else 300))
        metrics=batting({k:v*pa for k,v in rates.items()})
        base=batting(league); ops=metrics['ops']; baseline=base['ops']
        score=100*ops/baseline if ops and baseline else 100
        result={**metrics,'pa':round(pa),'ops_index':round(score),'hr':round(metrics['hr']),
                'bb':round(metrics['bb']),'k':round(metrics['k'])}
    else:
        ip=workload if workload is not None else min(190,max(30,number(recent[0].get('outs'))/3 if recent else 60))
        bf=ip/max(rates['outs']/3,0.15)
        metrics=pitching({k:v*bf for k,v in rates.items()},fip_constant(league))
        base=pitching(league,fip_constant(league)); score=100*base['fip']/metrics['fip'] if metrics['fip'] and metrics['fip']>0 else 100
        result={**metrics,'ip':round(ip),'quality_index':round(score),'k':round(metrics['k']),'bb':round(metrics['bb'])}
    # Approximate sampling sensitivity only, not an empirically calibrated prediction interval.
    result.update({'observed_exposure':round(observed),'evidence':'Established' if observed>=1000 else 'Limited' if observed>=200 else 'League prior',
                   'prior_weight':round(prior/denom,3),'method':VERSION,'kind':kind,
                   'caveat':'Rate baseline; playing time is a scenario. No aging, park, injury or ratings adjustment. No MLB history means league-average prior.'})
    return result

def backtest(histories, baselines, kind):
    output=[]; metric='ops' if kind=='bat' else 'fip'; exposure='pa' if kind=='bat' else 'outs'
    for year in range(2022,2026):
        errors=[]; naive=[]
        league=baselines.get(year-1)
        if not league: continue
        for history in histories.values():
            target=next((r for r in history if r['year']==year),None)
            previous=next((r for r in history if r['year']==year-1),None)
            if not target or not previous or number(target.get(exposure))<(200 if kind=='bat' else 150): continue
            if number(previous.get(exposure))<(100 if kind=='bat' else 90): continue
            forecast=projection(history,year,league,kind)
            calc=batting if kind=='bat' else lambda s:pitching(s,fip_constant(league))
            actual=calc(target)[metric]; last=calc(previous)[metric]
            if actual is None or last is None: continue
            errors.append(abs(forecast[metric]-actual)); naive.append(abs(last-actual))
        output.append({'year':year,'players':len(errors),'metric':metric.upper(),
                       'model_mae':rounded(sum(errors)/len(errors),4) if errors else None,
                       'last_season_mae':rounded(sum(naive)/len(naive),4) if naive else None})
    return output

def empirical_range(histories,baselines,kind):
    """Residual range calibrated on 2022–24; 2025 coverage is held out.
    Applies to rate forecasts, not season counts, rookies or player-specific risks.
    """
    residuals=[];holdout=[];metric='ops' if kind=='bat' else 'fip';exposure='pa' if kind=='bat' else 'outs'
    for year in range(2022,2026):
        league=baselines.get(year-1)
        if not league:continue
        for history in histories.values():
            target=next((r for r in history if r['year']==year),None)
            previous=next((r for r in history if r['year']==year-1),None)
            if not target or not previous or number(target.get(exposure))<(200 if kind=='bat' else 150) or number(previous.get(exposure))<(100 if kind=='bat' else 90):continue
            p=projection(history,year,league,kind)
            actual=(batting(target) if kind=='bat' else pitching(target,fip_constant(league)))[metric]
            if actual is not None:(holdout if year==2025 else residuals).append(actual-p[metric])
    residuals.sort()
    if not residuals:return None
    lo=residuals[int(.1*(len(residuals)-1))];hi=residuals[int(.9*(len(residuals)-1))]
    return {'metric':metric,'low_residual':lo,'high_residual':hi,'calibration_players':len(residuals),
            'held_out_players':len(holdout),'held_out_coverage':sum(lo<=x<=hi for x in holdout)/len(holdout) if holdout else None,
            'note':'Central 80% historical residual range from 2022–24 eligible players; checked on 2025. Pooled across players, not personalized or validated on future OOTP simulations. Not used for players with under 100 prior PA / 90 prior outs.'}
