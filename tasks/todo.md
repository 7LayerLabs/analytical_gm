# Project: Fenway Front Office (repo: 7LayerLabs/analytical_gm)

## Problem Statement
Claude took ownership of the project on 2026-10-01 (previously built by Milo, 12 commits Sep 30 - Oct 1).
The app works: 14 tabs, 128/128 tests pass, no browser console errors, careful "no fabricated
data" labeling, localhost-only server with CSP. But it is hard to maintain, its storage grows
without limit inside OneDrive, and its forecasts have never been checked against results.
Goal: make it safe to change, stop the disk growth, then prove the numbers.

## Assessment (2026-10-01)
- Working copy: `C:\Users\Derek\OneDrive\Documents\OOTP-Assistant` (only copy; stray clone deleted).
- Running: `pythonw server.py` on 127.0.0.1:8765. Save `mbltest`, Boston (team 4, league 203), game date 2026-07-01.
- Stack: Python 3.13 stdlib http.server + DuckDB 1.5.6; vanilla JS front end; no build step.
- Code is hand-compressed: `web/app.js` is 63 KB on 65 lines, Python lines up to 677 chars,
  semicolon-chained statements. Diffs and reviews are close to unreadable.
- `data/` = 2.2 GB after 5 snapshots in ~1 day (~440 MB each: full CSV copy + DuckDB). No retention.
  It sits in OneDrive, which syncs every GB and is a known risk for database files.
- Live-save tests call `import_snapshot()` against the real `data/` folder: they can create real
  snapshots and race the server's own import (one test failed mid-export tonight, passed after).
- Forecast models (Forecast 2026.1, roster-runs-1.1) are unvalidated; the app already archives each
  prediction, so calibration is possible as the season advances.
- Global git identity on this PC is `Milo <milobuilds@outlook.com>`; commits would be attributed to Milo.

## Plan
### Phase 0: Take over cleanly
- [x] Milo is done with this repo (Derek, 2026-10-01)
- [x] Commit identity: repo-local 7LayerLabs noreply

### Phase 1: Make it safe to change (zero behavior change)
- [x] Record every API route's JSON output for the current snapshot (baseline: 80 responses)
- [x] Auto-format Python (black) and web files (prettier) in one commit (db9f27d)
- [x] Verify: tests pass, API outputs identical to baseline, all 14 tabs render with no console errors
- [x] Stop the live-save test from importing into the real data folder (fdf27f2)

### Guiding principle (Derek, 2026-10-01)
"An assistant GM with access to an analytical department", not an analytics department.
Real players, real value, real wording. On the surface: the call, names, dollars, wins, years.
No "n over x", percentiles, cohorts or "preference grade" up front; the analytics department's
work lives one click down under "See the numbers". Confidence is said plainly (strong / lean),
not buried in disclaimers.

### Agreed with Derek (2026-10-01)
- Call scale: Do it / Do it if... / Don't / Hang up (can modify later)
- Dollar values: yes ("you give $148M, you get $17M")
- "Will the AI accept" prediction: PARKED until Derek decides
- Identities: Theo's set plus the current-app ones Derek likes (bring a merged list at D5)
- Order: trades -> signings/extensions/promotions -> Theo fold-in; storage fix slotted in between

### Phase D: Decisive answers
Derek's problem (2026-10-01): "not giving definitive answers, no strong suggestions, no pro/cons of making a trade".
Evidence from the current app (snapshot 2026-07-01):
- Trade Roman Anthony (22, 10/10 now and potential, signed through 2034) for reliever Cade Smith -> "Revise the package". Should be an emphatic no.
- Signing free agent Ryan Jeffers -> answers about internal catcher Carlos Narvaez instead; never says sign or pass.
- Anthony extension at $20M x 5 -> "No clear winner until cost and availability are confirmed."
- Every case repeats the same two "verify in OOTP" checks.
Draft steps (order and details to agree with Derek):
- [x] D1 Trade calls (trade_call.py, web/trade.js): call + strength, We give/We get dollar ledger, pros/cons naming players, who's in/out of lineup/rotation/bullpen, what would make it work (names real players on their side). Win-now premium by club direction. Analytics review folded under "See the numbers". Live since 2026-10-01.
- [x] D2 Value engine (value.py): dollars a player is worth to us over the years we control him. Calibrated per export from the save: rating->WAR lines (corr .80 bat / .76 SP / .65 RP), $/WAR from veteran deals ($6.8M), delta-method aging, development-to-potential by age; real MLB results blended in (2 seasons = half weight); two-way players add pitching; prospects valued as develop/stall mixture by level. 10 tests.
  - Known: mega-deals (Soto, Vlad) read deeply negative; partly real (ages 34-37), partly this league's $6.8M/win. Team/player options treated as scheduled years for now.
- [x] D3 Signings, extensions, call-ups (player_calls.py): same call scale + card; job read names the incumbent (take the job / split time / sit); extension separates already-controlled years from free-agent years and says "no need" when nothing is added. Live 2026-10-01.
- [x] D1b (Derek: "it's not talking stats") Trade pros/cons in baseball terms: role for us, this year's line, best tool, injury, contract tail. This-season wins from who plays instead of whom; holes named; contenders can't get a plain "Do it" on a deal that costs 0.75+ wins this year. Live 2026-10-01.
- [x] D1c (Derek's request) Compare trade offers (offers.py): player/package on the block + 2-4 offers -> one verdict (take / take once his spot is covered / counter / keep him), reasons vs runner-up by club direction, ranked table with tags, each offer's full card, saveable. Live 2026-10-01.
- [ ] D1d Signing/extension/call-up pros & cons in the same baseball voice (still partly "projects around X wins")
- [ ] D3b Replacement (injury cover) and deadline-plan questions still use the old department read
- [ ] D4 Assistant-GM voice everywhere else: Clubhouse read -> "your top moves this week" (biggest hole + best fix by name/dollars), player reports lead with value line + keep/trade/extend call, Find help ranked by value per dollar, button copy ("Get the department's read"), strip repeated boilerplate checks
- [ ] D5 Theo Scout fold-in (only the parts that earn their place): identity weights that change rankings, hunt list, exit-velo/barrel data; one identity set, not two

### Theo Scout overlap (2026-10-01)
- Theo: 10 identities with real weight vectors + voice lines; hunts other clubs for fits that beat your weak spots; uses exit velo/barrels from game logs.
- Front Office: 10 identities, but the grade is mostly fixed (65% rating + 35% MLB rate + park fit), so identity barely changes who ranks high; README lists Statcast as unexported/unknown.
- Overlapping pairs: Classic Moneyball~moneyball, Big Market~powerhouse, Tampa Farm~farm. Theo-only: New Moneyball/Process, Pitching Factory, Gloves & Contact, Platoon Engine, Durability Shop, Aging-Curve Pirate.

### Phase 2: Storage hygiene (done 2026-10-01)
- [x] Snapshots moved to %LOCALAPPDATA%\OOTP-Analytics\snapshots; state stays in data/ (OneDrive-backed). Newest 20 kept, raw CSV only on newest. data/ 2.5 GB -> 2.4 MB.
- [x] Stale Sep 30 failed import moved to %LOCALAPPDATA%\OOTP-Analyticsailed-imports-2026-09-30 (safe to delete)
- Saved cases store their own reports, so no pinning needed

### Phase 3: Prove the numbers
- [ ] Forecast calibration: compare archived predictions against actual records as exports accumulate; show the error honestly on the Clubhouse card
- [ ] Department grade sanity check against in-game outcomes (later, needs a full season of exports)

### Phase 4: Direction (Derek decides)
- [ ] Fold GM Portal / Theo Scout ideas into this app instead of keeping three OOTP companions?
- [ ] Generalize beyond Boston (any team / any save), e.g. for the future online league?

## Progress Notes
- 2026-10-01: Took ownership. Deleted duplicate clone at C:\Users\Derek\analytical_gm. Ran tests (128/128 after export settled), opened app, confirmed server runs latest commit 8d60b31.
- 2026-10-01: Phase 1 done. Formatting verified on isolated copies (ports 8791/8792, never touching live data): black --safe AST check, esbuild-minified JS identical, 80 API responses byte-identical, 14 tabs identical text/styles/layout, 128/128 tests. Live app (8765) still runs pre-format code, which behaves identically; restart whenever convenient.

## Review
(to be filled in as phases complete)
