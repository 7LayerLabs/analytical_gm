# Project: Fenway Front Office (repo: 7LayerLabs/analytical_gm)

## START HERE (last updated 2026-10-01)

**What this is:** a local OOTP 27 companion for Derek's Red Sox save. Direction (Derek): *an assistant GM
with access to an analytical department* — real players, real value (dollars), real wording; the
analytics live one click down under "See the numbers". Claude owns the project (took over from Milo,
2026-10-01).

**Status:** the Decision Lab now gives assistant-GM calls (Do it / Do it if... / Don't / Hang up, marked
strong or lean) for trades, signings, extensions and call-ups, plus a "Compare trade offers" question.
All built on a dollar-value engine calibrated from the save on every export. The Clubhouse leads with
the assistant GM's suggested moves (chains + comparisons with league-ranked stat lines). Nav: Clubhouse,
Trades, Decisions, Roster, Scouting, Find help, Farm, More. 165 tests pass.

### What's left, in order
1. **Baseball pros/cons for signings, extensions, call-ups** (D1d). Trades already talk baseball (role,
   stat line, best tool, injury, contract). Signing/extension/call-up cards still lean on
   "projects around X wins". Reuse `trade_call.scouting_line` + the analytics review's `people` data.
2. **Jev (TypeSafe) in the assistant GM** — PLAN WITH DEREK (spends TypeSafe credits; key is already set in
   TYPESAFE_API_KEY). Proposed: (a) "Is it real?" read on hot minor leaguers in Clubhouse moves (results vs
   ratings, e.g. Tolle), (b) a second opinion badge on trade calls (agrees / disagrees + confidence),
   on-demand buttons, cached per export. Existing hook: jev.review() on player reports.
2b. **Moves engine next steps:** biggest-hole fixes from outside (free agents / trade targets by name and
   dollars), not just internal call-ups; use the blueprint identity to weight suggestions.
3. **Player reports lead with the assistant GM** (D4). Value line from `value.py` + a keep / trade /
   extend call at the top; current analytics fold under "See the numbers".
4. **Find help ranked by value per dollar** (D4), in the same voice; strip the repeated boilerplate
   checks and remaining "department" copy across screens.
5. **Injury-replacement and trade-deadline questions** (D3b) still use the old department read; give
   them calls ("Use X", "Sell these three: ...").
6. **Identities merge with Theo Scout** (D5). Derek: "blueprint link doesn't work the way it should" —
   audit 2026-10-01 found it saves fine; likely complaint is that identities don't change any
   suggestions (confirm with Derek). WAITING ON DEREK: Theo's 10 are the base; which of the
   current app's 7 should stay? Old-school Baseball, Edgehunter, Trade Architect, Sustainable
   Contender, Homegrown Core, Stars & Support, Opportunity Buyer. Then make identities actually change
   rankings (Theo's weight vectors), add the "hunt other clubs" list and exit-velo/barrel data, and
   retire `Documents\Theo Scout\theo_scout.py`.
7. **Prove the numbers** (Phase 3). Grade archived season forecasts against actual records as exports
   accumulate; sanity-check value-engine calls against what happens in the sim.

### Open decisions for Derek
- Identities to keep (item 6 above).
- Price of a win: keep it calibrated from the save (~$6.8M, Claude's lean) or set it higher
  (real-MLB star deals run ~$8-9M per win; this is why Soto/Vlad mega-deals read so negative).
- "Will the AI accept this trade?" prediction: parked until Derek decides.
- Later: fold GM Portal ideas in; generalize beyond Boston (e.g. for the future online league).

### Known rough edges
- Moves: "Worth a look" only fires when the ratings gap is within ~1 win/season (0.3 for relievers).
- Team/player option years are treated as scheduled salary; options aren't judged yet.
- First Decision Lab review after a new export takes ~6s while the value engine calibrates.
- Pruning can leave empty `csv` folders in old snapshots (harmless).
- `%LOCALAPPDATA%\OOTP-Analytics\failed-imports-2026-09-30` is a stale failed import: safe to delete.
- README still describes the analytics department in detail; update it as screens change voice.

## Picking this up on another PC
1. **Get the code.** This folder lives in `OneDrive\Documents\OOTP-Assistant`, so if OneDrive syncs
   Documents on the other PC it is already there: open it and run `git pull`. Otherwise
   `git clone https://github.com/7LayerLabs/analytical_gm.git`. Keep ONE working copy per PC, and
   don't edit on two PCs at the same time (OneDrive also syncs the `.git` folder). Commit and push
   before switching PCs; pull when you arrive.
2. **Python 3.13** and `py -3.13 -m pip install -r requirements.txt` (DuckDB). For formatting:
   `py -3.13 -m pip install black` and Node (for `npx prettier@3`).
3. **`game-access.json` is not in git** (it's personal). If the folder came over through OneDrive it's
   there already; check `csv_directory` points at that PC's save
   (`...\OOTP Baseball 27\saved_games\mbltest.lg\import_export\csv`). On a fresh clone:
   `copy game-access.example.json game-access.json`, then set `csv_directory`, `team_id` 4,
   `league_id` 203.
4. **Export from OOTP first** (Game Settings → Database → Database Tools → Export data to CSV files,
   with "Show real player ratings"). Snapshots are per PC in `%LOCALAPPDATA%\OOTP-Analytics\snapshots`,
   so the first run imports that PC's export.
5. **Saved state** (blueprints, locks, journal, saved cases, forecast archive) lives in `data\` and is
   NOT in git. It travels only through OneDrive; a fresh clone starts blank.
6. **Run:** double-click `Start Front Office.cmd` → http://127.0.0.1:8765. The launcher reuses a
   running server, so after backend edits stop the `pythonw` process on port 8765 and launch again
   (from PowerShell: `Start-Process "...\Start Front Office.cmd"`).
7. **Tests:** `py -3.13 -m unittest discover -s tests` (live tests need an imported snapshot; don't run
   them while OOTP is mid-export).
8. **Before committing:** `py -3.13 -m black .` and `npx prettier@3 --write web`. Set a repo-local
   identity if that PC's default is wrong: `git config user.name "7LayerLabs"` and
   `git config user.email "222900153+7LayerLabs@users.noreply.github.com"`.
9. **Working with Claude there:** Claude's memory is per PC. Start with "read tasks/todo.md".

## Where the new code lives
- `value.py` — dollar value engine: projected WAR × price of a win − salary over the years we control a
  player. Calibrated per export: rating→WAR lines per role, price of a win from veteran deals,
  arbitration pay as a share of market, delta-method aging, development toward potential by age; real
  MLB results blended in; two-way players add pitching; prospects as a develop/stall mixture.
- `trade_call.py` — trade calls: ledger, baseball pros/cons, who-replaces-whom wins, holes, win-now guard.
- `player_calls.py` — signing, extension and call-up calls.
- `offers.py` — compare 2-4 offers for the same player(s) and pick one.
- `web/trade.js` — renders every call card, the offers comparison and the "See the numbers" fold.
- `storage.py` — snapshots outside OneDrive, newest 20 kept, raw CSV only on the newest.

## History
### Phase 0-1: Take over and make it safe to change (done 2026-10-01)
- Milo is done with the repo; commits go out as 7LayerLabs (repo-local).
- Reformatted everything with black/prettier (db9f27d), proven behavior-identical: black --safe AST
  check, esbuild-minified JS identical, 80 API responses byte-identical, all 14 tabs identical.
- Stopped the live-save test from importing into the real data folder (fdf27f2).

### Phase 2: Storage (done 2026-10-01)
- Snapshots moved to `%LOCALAPPDATA%\OOTP-Analytics\snapshots`; `data\` went from 2.5 GB to 2.4 MB.

### Phase D: Decisive answers
Derek's problem: "not giving definitive answers, no strong suggestions, no pro/cons of making a trade."
Agreed: call scale Do it / Do it if... / Don't / Hang up; values in dollars; identities = Theo's set plus
the current ones Derek likes; order trades → signings/extensions/promotions → Theo fold-in.
- [x] D2 value engine (94fe4aa)
- [x] D1 trade calls (541333e)
- [x] D3 signings, extensions, call-ups (c5612f8)
- [x] D1b trade pros/cons in baseball terms + who-replaces-whom wins + win-now guard (14c974a)
- [x] D1c compare trade offers (14c974a)
- [x] Day-to-day players treated as available (94b0607): OOTP flags DTD as injured; the app had pulled Early
  from the rotation and Story from SS.
- [x] Clubhouse assistant-GM moves + nav cleanup + Trades page (1e1d0a8). Full UI audit: 15 pages, 0 errors,
  0 failed requests; More menu, Trades tabs, all Decisions questions, player reports, older exports work.
- [ ] D1d, D3b, D4 (player reports, Find help), D5 — see "What's left" above

## Review
### Changes made (2026-10-01)
- Took over the project, reformatted it into readable code with zero behavior change, and fixed a test
  that could write into live data.
- Moved snapshot storage out of OneDrive with a retention cap.
- Built the dollar-value engine and assistant-GM calls for trades, signings, extensions, call-ups, and
  multi-offer comparison; the old analytics remain under "See the numbers".
- Files added: value.py, trade_call.py, player_calls.py, offers.py, tests for each, tasks/todo.md.
  Files changed: storage.py, server.py, department.py, frontoffice.py, web/trade.js, web/lab.js,
  web/app.js, web/style.css, README.md.

### Notes
- Every UI change was checked in the browser on an isolated copy (separate port and data) before going
  live; the live app's error log stayed empty.
- Real examples on the July 2026 save: Anthony for Cade Smith → Hang up ($151M for $25M); Gray for
  Kerkering + Stott → Do it if we can replace Gray (good value, 2.2 wins worse this year).
