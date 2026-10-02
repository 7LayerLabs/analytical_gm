"use strict";
function seasonPrediction(current) {
  if (!current) return "";
  if (current.error)
    return panel(
      "Roster prediction",
      `<p>${esc(current.error)}</p><small>Export the completed MLB history and regular-season schedule, then update files. An unsupported win total is not invented.</small>`,
    );
  const p = current,
    c = p.club,
    original = current.opening_forecast,
    delta = current.delta_original;
  const phase =
    c.remaining_games === 0
      ? "Final season record"
      : p.preseason
        ? "Current preseason prediction"
        : "Projected season finish";
  const injury =
    c.known_injury_win_effect < -0.05
      ? `${fmt(Math.abs(c.known_injury_win_effect), 1)} fewer expected wins than the healthy-roster scenario.`
      : "Ready internal coverage keeps the modeled injury effect small.";
  const depth = `${fmt(c.minor_pa)} hitter PA and ${fmt(c.minor_ip)} pitching innings come from plausible minor-league coverage.`;
  const rank = (n, total) => `${n} of ${total}`;
  const rows = p.division.map(
    (t) =>
      `<tr class="${t.team_id === c.team_id ? "our-projection" : ""}"><td>${esc(t.name)}</td><td>${t.wins}–${t.losses}</td></tr>`,
  );
  const change =
    delta == null
      ? ""
      : `<span class="forecast-delta ${delta > 0 ? "positive" : delta < 0 ? "negative" : ""}">${delta === 0 ? "Unchanged" : (delta > 0 ? "+" : "") + delta + " " + (Math.abs(delta) === 1 ? "win" : "wins")}</span>`;
  const baseline = original
    ? `<p class="forecast-original">Original prediction <b>${original.club.wins}–${original.club.losses}</b> · ${date(original.game_date)}</p>`
    : '<p class="forecast-original">Original preseason prediction was not captured.</p>';
  const archive = (current.archive || []).slice().reverse();
  const archiveRows = archive.map((r, i) => {
    const earlier = archive[i + 1],
      previous = earlier?.wins,
      changes = [];
    if (previous != null && previous !== r.wins)
      changes.push(
        `${r.wins - previous > 0 ? "+" : ""}${r.wins - previous} wins from previous estimate`,
      );
    if (earlier && r.version !== earlier.version) changes.push("Model updated");
    if (earlier?.roster?.length && r.roster?.length) {
      const old = new Map(earlier.roster.map((p) => [p.id, p.name])),
        now = new Map(r.roster.map((p) => [p.id, p.name]));
      const added = r.roster.filter((p) => !old.has(p.id)).map((p) => p.name),
        removed = earlier.roster.filter((p) => !now.has(p.id)).map((p) => p.name);
      if (added.length) changes.push("MLB roster additions: " + added.join(", "));
      if (removed.length) changes.push("MLB roster departures: " + removed.join(", "));
    }
    if (r.injuries?.length)
      changes.push(
        "Modeled absences: " +
          r.injuries.map((p) => p.name + " (" + p.games + " games)").join(", "),
      );
    if (!changes.length)
      changes.push(earlier ? "No change in rounded win total" : "First archived prediction");
    return `<tr><td>${date(r.game_date)}<small>${esc(r.version || "Original model")}</small></td><td><b>${r.wins}–${r.losses ?? "—"}</b><small>Actual ${r.actual_wins}–${r.actual_losses}</small><small>${r.delta_original == null ? "No original baseline" : (r.delta_original > 0 ? "+" : "") + r.delta_original + " vs original"}</small></td><td>${changes.map((x) => esc(x)).join("<br>")}</td></tr>`;
  });
  const workloads = p.workloads.map(
    (s) =>
      `<tr><td>${s.id ? link({ id: s.id, name: s.name }) : esc(s.name)}</td><td>${esc(s.position)}</td><td>${fmt(s.workload)} ${s.kind === "bat" ? "PA" : "IP"}</td><td>${s.minor ? "Minor-league coverage" : "MLB / fallback"}</td></tr>`,
  );
  return panel(
    "Roster prediction",
    `<div class="season-prediction"><span class="forecast-label">${phase} · ${p.year}</span><div class="forecast-record"><strong>${c.wins}–${c.losses}</strong>${change}</div>${baseline}<p class="forecast-range">Planning range: <b>${c.range.low}–${c.range.high} wins</b></p><p>${c.played_games ? `Actual record ${c.actual_wins}–${c.actual_losses}. Projects the remaining ${c.remaining_games} games using the latest roster.` : "Based on our roster against the rest of MLB, independent of our playoff goal."}</p><div class="forecast-ranks"><div><strong>${rank(c.division_rank, c.division_size)}</strong><small>${esc(c.division_name)}</small></div><div><strong>${rank(c.subleague_rank, c.subleague_size)}</strong><small>${esc(c.subleague_name)}</small></div><div><strong>${rank(c.mlb_rank, c.mlb_size)}</strong><small>MLB</small></div></div><p class="forecast-reading">${c.division_rank === 1 && p.division.length > 1 && c.expected_wins - p.division[1].expected_wins < 3 ? "A narrow division lead in this model. The gap is smaller than the forecast uncertainty." : c.wins >= 90 ? "The model sees a strong regular-season roster. Depth and availability still matter." : c.wins >= 85 ? "The model sees a competitive roster with a chance to contend. There is little room to assume every key player stays healthy." : c.wins >= 78 ? "The model sees a club near the middle of the pack. Improving depth or a weak everyday role could change the outlook." : "The model sees a roster that needs improvement to contend."}</p>${c.minor_pa || c.minor_ip ? '<p class="forecast-coverage-note">Includes plausible use of ready minor-league depth. Promotions and playing time are assumptions you can inspect below.</p>' : ""}${table(["Division comparison", "Projected record"], rows)}<details class="forecast-detail"><summary>Why this record?</summary><p><strong>Offense & pitching:</strong> ${c.runs_scored} estimated runs scored and ${c.runs_allowed} allowed ${c.played_games ? "over the remaining schedule" : "against the actual schedule"}.</p><p><strong>Known injuries:</strong> ${esc(injury)}</p><p><strong>Depth:</strong> ${esc(depth)} ${c.missing_pa || c.missing_ip ? `${fmt(c.missing_pa)} PA / ${fmt(c.missing_ip)} IP still use the replacement-level scenario.` : "The modeled workload has internal coverage."}</p><p><strong>Ballparks:</strong> ${Math.abs(c.park_win_effect) < 0.2 ? "The net park effect is small; both clubs play in the same venue." : `${fmt(c.park_win_effect, 1)} wins versus the same schedule in neutral parks.`} Uses actual venues and batting-side factors.</p><p><strong>Defense:</strong> ${fmt(c.defense_runs, 1)} estimated runs saved versus the model’s league mean. This uses a disclosed rating-to-run assumption.</p><details><summary>Injury assumptions</summary>${
      p.club.injuries.length
        ? table(
            ["Player", "Games before estimated recovery"],
            p.club.injuries.map(
              (i) =>
                `<tr><td>${esc(i.name)}</td><td>${i.games}${i.days_unknown ? " · recovery unknown; 30-day scenario" : ""}</td></tr>`,
            ),
          )
        : empty("No modeled injury absence at this export.")
    }</details></details><details class="forecast-detail"><summary>Roster & playing time used</summary>${table(["Player", "Role", "Workload", "Coverage"], workloads)}<p>These are inferred season assignments. Minor-league coverage requires game eligibility, roster room and development review.</p></details><details class="forecast-detail"><summary>All MLB projections</summary>${table(
      ["Club", "Record", "MLB rank"],
      p.league.map(
        (t, i) => `<tr><td>${esc(t.name)}</td><td>${t.wins}–${t.losses}</td><td>${i + 1}</td></tr>`,
      ),
    )}</details><details class="forecast-detail"><summary>Method & limitations</summary>${p.method.map((s) => `<p>${esc(s)}</p>`).join("")}<p>${p.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label)}</a>`).join(" · ")}</p></details><details class="forecast-detail"><summary>Prediction archive (${archive.length})</summary>${table(["Export date", "Prediction", "Context"], archiveRows)}<p>Every reviewed export is retained, including unchanged estimates. Roster and injury notes describe observed inputs; they do not isolate the exact cause of a win change.</p></details><p class="forecast-foot">Experimental model · planning range is not a confidence interval.<br>Roster captured ${date(p.game_date)}${current.opening_forecast ? " · preseason baseline preserved" : ""}.</p></div>`,
  );
}
