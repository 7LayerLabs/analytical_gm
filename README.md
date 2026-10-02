# Fenway Front Office

A local OOTP Baseball 27 analytics department, designed around a Boston Red Sox front office. The companion reads exports; it never advances the game or writes to the save.

## Set up and open

Requires Windows and Python 3.13 or later. Download or clone this repository, then run these commands in its folder:

```powershell
python -m pip install -r requirements.txt
Copy-Item game-access.example.json game-access.json
```

Edit `game-access.json`: set `csv_directory` to your OOTP save's `import_export/csv` folder, and use your save's actual `team_id` and `league_id`. Example IDs are placeholders; check `teams.csv` and `leagues.csv`. The interface currently uses Boston branding.

Complete a full OOTP CSV export, then double-click **Start Front Office.cmd**. It opens http://127.0.0.1:8765. You can also run `python server.py --open` in a terminal. Click **Update Files** to import. With no export, the application displays setup guidance. Files stay on your computer. Python and dependencies must be installed before using the launcher.

## Player reports

Reports start with one clear verdict and a fuller scouting assessment, with a smaller department grade beside it. Choose the intended position to refresh the recommendation and comparisons. Current ability, future upside and club fit are explained separately. The strongest practical organizational alternative includes readiness, defensive ability and roster costs; expanded alternatives include minor-league players and future options. Standing GM locks remain binding.

Skills compare inferred regular starters at the intended position first, then all assigned MLB hitters. Pitchers compare with starters or relievers first, then all MLB pitchers. Each comparison shows its sample, exact tied rank range and midpoint percentile. Hitter regulars use one qualified player per MLB team, prioritized by the previous completed season's starts, listed position and active status. These are inferred benchmarks, not confirmed exported depth charts. Power-rating ranks are not home-run leaderboards. Full stats, park evidence, contracts and history remain in their report tabs.

## Refresh the evidence

1. Finish an OOTP CSV export using Game Settings → Database → Database Tools → Export data to CSV files.
2. Click **Update Files**. The running companion also checks for completed stable exports every ten seconds.
3. Verify the game date in the header. The snapshot selector lets you examine previous exports.

Update Files reads existing CSVs; it does not make OOTP export. Failed imports preserve the prior valid snapshot. Each snapshot retains all 70 source CSVs, a DuckDB database, file hashes, row counts and a manifest. Allow disk space for approximately 234 MB of CSVs per capture plus its database. No unexported date has a synthetic rating history.

## The redesigned department

- **Clubhouse:** short club briefing, a separate goal-independent preseason win projection beneath the saved plan, five-slot rotation profile, defensive diamond, priorities, saved plan, watchlist and changes since the preceding export.
- **Team blueprint:** separate season directions, combinable identities, playing philosophy, skill priorities and guardrails. Original Moneyball and Edgehunter are separate identities. Saved versions preserve the prior plan, reason, game date and export.
- **Roster lab:** left/right lineups, global defensive position assignment, speed/defense preferences, a five-player rotation, up to eight relievers and four bench bats. Include healthy minor-league options to compare internal replacements. Explicit lineup, batting-slot, position, rotation, bullpen, roster and trade-protection locks remain saved until the GM removes them. Conflicts and unavailable locked players produce warnings.
- **Scouting:** compact player rows and six report tabs: Overview, Skills, Performance, Team fit, Contract and Decision history. Current and potential ratings remain distinct. League skill percentiles show lower/tied/higher shares and their cohort. Contracts include the full schedule, option types, buyouts, incentives, signed extensions and service/roster fields.
- **Find help:** free agents, other-club research targets, internal alternatives and selective-sale candidates. Skill profiles and park-fit evidence accompany suggestions. Trade-block code mapping is unverified and is explicitly labeled, rather than inventing availability.
- **Money & contracts:** exported cash-trades-available field first, budget/payroll context, seven-year salary chart, conditional options, expiring schedules, and next-year ordinary arbitration review. Signed contract/extension coverage excludes a player from that review. The game-payroll reconciliation gap stays visible.
- **The pipeline:** organizational potential, development changes, position depth and an export-flagged draft board. Potential tier leads; positional scarcity breaks ties within a tier. Draft availability and signing demands need game confirmation.
- **Decision Lab:** start with one of six plain-language questions, then search players by name. Only relevant inputs appear; offer terms, service assumptions and a direction override live under More options. Replacement, promotion, signing, trade, extension and deadline cases. Includes doing nothing, internal/external alternatives, costs, service illustrations, next-season considerations and checks. Trade packages can be assembled by name. An explicitly unlocked scenario does not change standing protection. Save cases as Exploring, Chosen, Applied in OOTP or Revisit.
- **Around the league:** season selection, hitter/pitcher leader categories, a reliever workload group, current standings, tie-aware 1–10 rating distributions, empirical stat standards and labels for three seasonal checkpoints.
- **GM notebook:** notes, watchlists, locks and saved decision timelines.
- **Field guide:** searchable definitions, hover/focus help, source/method information and the Jev connection.

The presentation uses a light paper background, navy navigation, condensed headlines/player names and readable body type. Reports use tabs and compact lists. 

## What the numbers mean

**Facts:** exported ratings, contracts, counts, service status and park factors. Season totals use split_id=1 and game_id=0, combining team stints within player/year/league without adding platoon rows. Innings use outs/3 and baseball display notation.

**Forecast 2026.1:** the previous three completed MLB seasons use 5/4/3 recency weights with a 300-PA hitter prior or 200-BF pitcher prior. It has no aging, rating, injury or park correction. A player without MLB history receives a league baseline, not a personalized minor-to-major forecast. OPS index is not OPS+ or wRC+. Historical pooled error bands are not individualized guarantees. Backtests do not establish future OOTP simulation accuracy.

**Department grade:** a transparent, uncalibrated 1–10 preference score: 65% current rating preference plus 35% conservative MLB rate score, with a bounded ±0.4 park-fit preference adjustment. It is not predicted WAR, market value or wins. Moneyball and selected essential offensive/pitching skills adjust the displayed component weights. Contact's BABIP component is not added again to contact. Playing philosophy, speed and defense affect the lineup assignment separately.

**Percentiles:** percentage lower plus half of tied percentage, with hitter/starter/reliever cohorts of currently assigned MLB players. A rating of 5 is not presumed average. Starter/reliever classification uses stamina and recent MLB usage. Qualification thresholds and sample sizes are displayed.

**Park fit:** regular-season venue counts come from the actual exported schedule. Weighted factors are preference context, not a promise of an exact change in player outcomes. Switch-hitter HR fit uses the overall factor when future opposing handedness is unknown.

**Contracts:** salary0 anchors to season_year. A signed extension replaces an overlapping scheduled year rather than being added twice. Conditional options, opt-out/retention codes, bonuses, renewals and arbitration still require game confirmation. Exported cash_trades_available is labeled pending UI reconciliation; owner budget less payroll is not asserted to be spendable cash.

**Promotion:** service-day illustrations are user assumptions, not a guaranteed extra year of control or Super Two calculation. Confirm active/40-man roster counts, options, injury eligibility, deadlines and playing time in OOTP. No universal safe debut date is invented.

**Unknowns:** trade-block mapping, asking prices, acceptance, precise move legality, and unexported Statcast metrics. CSV split codes 2/3 have not been verified against handedness labels; recommendations use the explicitly named vs-L/vs-R ratings.

## Jev

An optional TypeSafe key can be remembered with Windows DPAPI under `%LOCALAPPDATA%/OOTP-Analytics/jev-key.bin`, outside OneDrive. **Field guide → Jev connection** can update it. Reports offer **Ask Jev for a second read**. Reviews send the player's profile, selected ratings and evidence to the hosted TypeSafe API, consume account credits when not cached, and validate typed choices/confidence. The department still supplies the complete summary and performs all arithmetic. Low-confidence classifications are marked provisional; classification confidence is not a baseball outcome probability. 

## Storage and verification

`game-access.json` selects the source save, team and league. `data/frontoffice-team4-league203.json` stores blueprint versions, locks, watchlists, checkpoints and saved cases; `data/journal.json` stores notes. Snapshot data remains separate. The app binds to 127.0.0.1 and rejects external origins for mutations. Credentials are not in these state files.

Run `python -m unittest discover -s tests -q` for mathematical, import, contract and department checks. The redesign has also been checked in the browser at desktop and 390-pixel widths, including navigation, report tabs, league tabs, case evaluation/saving, and a live Jev review. Live-save integration tests run when a local imported snapshot exists; portable unit tests run without private exports.

If the export looks stale, export again from OOTP. If an import fails, read the banner; the previous capture remains available. Server diagnostics are in `data/server-error.log`. After editing backend code, restart this app's server; the desktop launcher reuses an already running process.

## Publication and privacy

The repository excludes CSV exports, databases, snapshots, personal configuration, saved decisions, logs and credentials. Copy the example configuration locally; never commit your API key. Jev is optional: the department summaries and calculations work without it. Its explicit review action sends selected player evidence to TypeSafe. The application reads exports and never executes roster transactions or advances OOTP.

An optional GitHub Actions test template is in ci/github-actions.yml. Copy it to .github/workflows/tests.yml using a GitHub sign-in with workflow permission to enable automated repository checks.

## Season predictions and archive

The Clubhouse sidebar shows projected wins, a planning range, division comparisons and American/National League and MLB ranks. Expand the card for inferred playing time, known injuries, minor-league coverage, park effects and the complete league forecast. The first pre-opening capture is retained in a local file scoped to the source save, team, league and season; the headline updates to the latest expected final record, shows the change in wins from the original, and keeps that original record underneath. Each completed export is automatically archived locally, even when another page is open. The expandable Prediction archive lists dates, records, changes, actual records and observed roster/injury context; revisiting a capture does not duplicate or replace its forecast. A first midseason import does not invent an Opening Day forecast.

The experimental roster-runs-1.1 model uses a fixed policy across scheduled MLB clubs, independent of goals, identities and locks. Current-season MLB performance (weight 1.2), previous three completed MLB seasons (1/.8/.6), and rating-conditioned event priors estimate player rates. These priors borrow same-rating groups' last completed MLB performance and are not a validated historical-ratings forecasting model. Historical team stints use approximate half-home park neutralization with the currently exported factors. The actual schedule supplies opponents and venues, applying batting-side park factors to both clubs.

Nine positional regulars receive 85% of a positional PA budget before known injury absences; reserve capacity is shared across positions. Five starters and up to eight relievers have capped history-informed innings, followed by bounded ready-depth coverage. Minor candidates must be AAA/AA or on the secondary roster and meet a fixed active-MLB 25th-percentile skill threshold. Unfilled work uses an explicitly assumed 20th-percentile offense / 80th-percentile FIP fallback. Unknown recovery uses a labeled 30-calendar-day scenario. Actual promotions and future transactions are not assumed to be guaranteed.

BaseRuns' advancement multiplier matches the last completed MLB run environment. Pitching FIP differences shift league runs allowed. Defense uses a disclosed assumption of 2 runs per positional-rating point relative to the modeled league mean. Opponent-specific run matchups use exponent 1.83, and every scheduled game distributes exactly one expected win between the clubs. Rounded records preserve total league wins. The ±10-win planning range widens for limited history and coverage gaps; it is not a calibrated confidence interval. No playoff probability is claimed.

This model has not been validated against future OOTP simulation results. Historical park changes, precise future workload, framing, aging, bullpen leverage, future injuries and some baserunning remain limitations. In-season estimates keep actual wins/losses from team_record and forecast only unplayed schedule games. If standings and the completed schedule disagree, the app requests a fresh complete export. Planning ranges narrow with remaining games and never cross already banked results; at season end the prediction becomes the actual final record. Archive files are scoped by source save, team, league and year, and include model version; a model update is labeled separately from observed roster changes. See the card's linked [BaseRuns formulation](https://blogs.fangraphs.com/fun-with-baseruns/) and [MLB run-based winning expectation](https://www.mlb.com/glossary/advanced-stats/pythagorean-winning-percentage) references for the underlying run mathematics.

### Generated playing styles and MLB readiness

The team blueprint drafts How we play from selected How we build identities. The primary identity receives twice each supporting identity's weight. Mixed philosophies become Blended. Any field can be customized; customized fields survive identity changes and saved blueprint versions. Reset restores generated priorities. Generation is a transparent rules-based draft, not an AI claim of optimized baseball strategy.

MLB readiness searches the Red Sox organization, any of the other 29 MLB organizations, or all organizations. Reviews separate current ability from future potential, show actual recent stats and league-relative performance, compare inferred MLB roles (including each rotation spot), and explain park/schedule fit, injuries, development, contract and roster/service considerations. Role, handedness, evidence and costs have separate views.

Readiness verdicts use explicit screening thresholds and are not calibrated outcome probabilities. Minor-league stats are never presented as MLB equivalents. Other clubs use their own roster and park context; own-team locks remain binding. Exported service totals do not prove a safe Super Two date or move legality. Review the game before making roster moves.

### Pitching roles and workload plan

Roster Lab shows OOTP primary relief roles, usage recommendations, secondary Emergency SP coverage when supported, and an explained initial pitch cap for each starter. Selected pitchers' full scouting reports include the same plan. Fixed current-tool weights rank relief quality; stamina, repertoire, rated splits and historical MLB workload determine role eligibility and deployment. Established starting pitch history, prior innings and youth can lower the disclosed stamina-based cap. Missing stamina or throwing availability yields no usable cap.

The plan flags long-relief coverage gaps and recent exported work/fatigue. Pitch caps are planning ceilings, not targets, clearance decisions or proven injury-prevention thresholds; verify spring/rehab buildup and today's rest. Analytics-led plans can recommend a Stopper; its exact inning/lead dropdown remains unverified because it was not shown in the supplied menus. Every recommendation remains an app suggestion, and GM locks retain their force. No game settings are changed.

### Acquisition realism

Find Help defaults to need-based inquiries and puts free-agent inquiries first. It compares current roles with plausible preference improvements, instead of ranking the entire league by payroll and grade. A separate premium-target view retains young elite-upside players, high-current-value players, and strong controlled assets. Low scheduled salary, limited statistical history, and one-year salary entries never establish cheap trade cost or one year of team control. Langford's exported 24-year-old, overall-potential-10, defense-8 profile is explicitly excluded from the default inquiry and Edgehunter lists.

Every acquisition card separates payroll from asking price, shows current/potential ratings, service-control context, role comparison, park fit and GM-lock constraints. Trade availability and asking packages remain unconfirmed. These are conservative screening rules, not a learned trade-value model or a claim that another club will sell. No draft-pick/prospect package, retained salary, financial capacity or acceptance probability is fabricated.

### Core and trade plan

Core & trade plan reads the saved now/next-season windows and separates build-around foundations, development cornerstones, current-window pillars, conditional trade discussions and explicit GM trade protection. Each player has age, current/potential ratings, conservative MLB performance assessment, contract/service context, park fit and named positional alternatives. Foundation ordering balances current tools, upside and performance preference; weaker performance gets earlier review among otherwise similar conditional trade candidates.

Surplus requires actual comparable healthy MLB coverage; untested minor-league upside does not make a player expendable. SP surplus keeps five starters plus another comparable active option. Trades that could weaken next season's contender are conditional on a replacement path and a worthwhile return. GM locks remain binding. A development cornerstone is not automatically MLB-ready, and the app never lists a player on OOTP's trading block or executes a transaction.

Roster lab now pairs selected minor-league alternatives with a named outgoing MLB assignment review. It separates active and 40-man space, option history, must-be-active restrictions, veteran consent, development playing time and readiness. AAA assignments remain conditional; no DFA, waiver clearance or remaining option is assumed. Unselected preseason players are listed as additional assignment reviews.

Owner goals are saved by season with the owner's letter, categories, deadlines, progress notes, version history and a fixed opening baseline. Active goals appear in Clubhouse, Decision Lab, acquisitions and optional Jev context. Position upgrades receive additional inquiry priority without bypassing cost/fit screens. Multi-season goals carry forward until their deadline. Fan-interest changes are observed CSV facts; owner completion is recorded manually from OOTP. The win forecast and saved locks remain independent.

Trade reviews lead with an explicit verdict and compare inferred MLB assignments before/after against both pitcher hands, plus a package-injury recovery scenario. Current overall, potential, age, observed MLB stats, contracts and named roles explain the talent cost. A disclosed young-core screen guards against treating two role players as equal to one foundational asset. Average assigned-player grades are preference diagnostics, not wins or summed package trade value. Missing renewal/arbitration salaries are labeled incomplete; future commitment reductions are never called net savings. Owner impact is assessed on the proposed package. Older saved reviews retain their original evidence and require a new review for this format.
