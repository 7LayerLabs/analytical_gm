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

### Phase D: Decisive answers (DRAFT, planning with Derek, nothing built)
Derek's problem (2026-10-01): "not giving definitive answers, no strong suggestions, no pro/cons of making a trade".
Evidence from the current app (snapshot 2026-07-01):
- Trade Roman Anthony (22, 10/10 now and potential, signed through 2034) for reliever Cade Smith -> "Revise the package". Should be an emphatic no.
- Signing free agent Ryan Jeffers -> answers about internal catcher Carlos Narvaez instead; never says sign or pass.
- Anthony extension at $20M x 5 -> "No clear winner until cost and availability are confirmed."
- Every case repeats the same two "verify in OOTP" checks.
Draft steps (order and details to agree with Derek):
- [ ] D1 Trade calls: one call (Do it / Do it if... / Don't / Hang up) + strength, pros/cons with numbers, "what would make it work", "will the AI accept"
- [ ] D2 Value engine behind D1: surplus value (projected WAR x $/WAR - salary over years of control) plus OOTP's own exported overall/talent value for AI acceptance
- [ ] D3 Same treatment for signings (sign at <= $X for <= N years / pass), extensions, promotions
- [ ] D4 Strip repeated boilerplate checks; one global "make moves in OOTP" footnote
- [ ] D5 Theo Scout fold-in (only the parts that earn their place): identity weights that change rankings, hunt list, exit-velo/barrel data; one identity set, not two

### Theo Scout overlap (2026-10-01)
- Theo: 10 identities with real weight vectors + voice lines; hunts other clubs for fits that beat your weak spots; uses exit velo/barrels from game logs.
- Front Office: 10 identities, but the grade is mostly fixed (65% rating + 35% MLB rate + park fit), so identity barely changes who ranks high; README lists Statcast as unexported/unknown.
- Overlapping pairs: Classic Moneyball~moneyball, Big Market~powerhouse, Tampa Farm~farm. Theo-only: New Moneyball/Process, Pitching Factory, Gloves & Contact, Platoon Engine, Durability Shop, Aging-Curve Pirate.

### Phase 2: Storage hygiene
- [ ] Retention: keep the latest N snapshots plus any snapshot a saved case or forecast references; allow pinning
- [ ] Move `data/` out of OneDrive (e.g. `%LOCALAPPDATA%\OOTP-Analytics`, where the Jev key already lives), migrate existing data once

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
