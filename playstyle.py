"""Inspectable playing-style drafts from the GM's building identities."""
RULES={
 'moneyball':('Analytics-led',{'On-base ability':3,'Power':1,'Control':3,'Platoon versatility':3},'Put dependable on-base hitters near the top, make pitchers work, and use affordable platoon complements.'),
 'edgehunter':('Analytics-led',{'Platoon versatility':3,'Defense up the middle':3,'On-base ability':3},'Use handedness, defense and park fit to turn overlooked skills into useful roles; test the edge rather than assuming it exists.'),
 'farm':('Blended',{'Pitching depth':3,'Durability':3,'Contact':3},'Give developing players clear roles and regular work, with internal coverage behind the MLB lineup and rotation.'),
 'powerhouse':('Blended',{'Power':3,'Pitching depth':3,'Strikeouts':3,'Durability':3},'Build around impact bats and strong pitching, then protect those pillars with reliable backups.'),
 'trader':('Analytics-led',{'Platoon versatility':3,'Pitching depth':3},'Define the role an acquisition must fill before making a deal; trade from surplus without opening another hole.'),
 'sustainable':('Blended',{'Pitching depth':3,'Durability':3,'Defense up the middle':3},'Keep useful depth around the core and avoid short-term assignments that weaken next season’s coverage.'),
 'homegrown':('Blended',{'Contact':3,'Pitching depth':3},'Create playing-time paths for the homegrown core and use outside veterans to complement it.'),
 'stars':('Blended',{'Power':3,'Strikeouts':3,'Platoon versatility':3,'Pitching depth':3},'Let the stars carry high-impact roles, with matchup complements and coverage for the back end of the staff.'),
 'opportunity':('Analytics-led',{'Platoon versatility':3,'Durability':3},'Keep flexible bench and pitching roles so a rebound candidate can help without forcing a permanent commitment.'),
 'traditional':('Traditional',{'Speed':3,'Contact':3,'Defense up the middle':3,'On-base ability':2},'Use speed near the top, the strongest bat third and a power bat fourth; emphasize contact, defense and purposeful baserunning.')
}

def generate_style(identities,skills):
    if len(identities)!=len(set(identities)) or any(i not in RULES for i in identities):raise ValueError('Choose supported, distinct building identities.')
    if not identities:return {'philosophy':'Blended','skills':{s:'Preferred' for s in skills},'playing_notes':'Choose a building identity to draft our playing approach.','source':[],'explanation':'No identity selected; priorities are neutral.'}
    modes={RULES[i][0] for i in identities};philosophy=next(iter(modes)) if len(modes)==1 else 'Blended'
    weights=[2]+[1]*(len(identities)-1);total=sum(weights);priorities={}
    for skill in skills:
        score=sum(RULES[i][1].get(skill,2)*w for i,w in zip(identities,weights))/total
        priorities[skill]='Essential' if score>=2.5 else 'Optional' if score<1.5 else 'Preferred'
    return {'philosophy':philosophy,'skills':priorities,'playing_notes':' '.join(RULES[i][2] for i in identities),'source':list(identities),'explanation':'The primary identity has twice the influence of each supporting identity. Mixed philosophies produce a blended approach. Your custom edits take precedence.'}
