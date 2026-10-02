"use strict";

let RD = { team: null, q: "", minor: true, offset: 0, player: null, role: "", hand: "vsr" };

async function readiness() {
  if (RD.team === null) RD.team = ourTeam();
  const r = await api("/api/office/readiness-list", {
    team: RD.team,
    q: RD.q,
    minor: RD.minor ? "1" : "0",
    offset: RD.offset,
  });
  return (
    head(
      "Ready for the majors?",
      "Current talent, performance at his actual level, and the MLB job he could earn.",
      "PROMOTION DESK",
    ) +
    `<div class="filters"><label>Organization<select id="ready-team"><option value="0" ${Number(RD.team) === 0 ? "selected" : ""}>All MLB organizations</option>${r.clubs.map((c) => `<option value="${c.id}" ${Number(RD.team) === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label><label>Player<input id="ready-search" type="search" placeholder="Search by name" value="${esc(RD.q)}"></label><label><input id="ready-minor" type="checkbox" ${RD.minor ? "checked" : ""}> Call-up candidates only</label></div><div class="readiness-layout"><div>${panel("Find a player", r.players.map((p) => `<article class="ready-candidate"><div><button data-ready="${p.id}" data-org="${p.organization_id}" class="player-name">${esc(p.name)}</button> ${badge(p.position)}${p.injured ? badge("Unavailable", "red") : ""}<small>${esc(p.organization)} · ${esc(p.team)} · age ${p.age}</small><p>Current tools: ${p.current_percentile == null ? "not fully exported" : fmt(p.current_percentile) + "th percentile among MLB " + (p.kind === "bat" ? "hitters" : "role pitchers")}</p></div><div><b>${fmt(p.current, 1)} <small>current / 10</small></b><small>${fmt(p.potential, 1)} potential / 10</small></div></article>`).join("") || empty("No matching players. Try including the MLB roster."))}<div class="pagination"><small>${r.total} matches</small><button id="ready-prev" ${RD.offset === 0 ? "disabled" : ""}>Previous</button><button id="ready-next" ${RD.offset + 12 >= r.total ? "disabled" : ""}>Next</button></div>${note(r.note)}</div><div id="ready-review">${empty("Select a player to review his readiness and the actual MLB role he could fill.")}</div></div>`
  );
}

function readinessReport(r) {
  const p = r.player,
    bat = p.kind === "bat",
    roles = bat ? ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"] : ["SP", "RP"],
    stats = r.stats,
    levels = {
      1: "MLB",
      2: "AAA",
      3: "AA",
      4: "Lower minors",
      5: "Lower minors",
      6: "Lower minors",
      7: "Lower minors",
    };
  return `<article class="lead ready-verdict"><span class="eyebrow">${esc(r.organization)} · ${esc(r.role)} REVIEW</span><h2>${esc(p.name)}: ${esc(r.status.toLowerCase())}.</h2><p>${esc(r.reason)}</p><div class="metrics">${metric("Current tools", fmt(r.current, 1) + "/10", fmt(r.current_context.percentile) + "th percentile · " + r.current_context.n + " MLB role peers")}${metric("Future potential", fmt(r.potential, 1) + "/10", "Upside is separate from readiness")}</div></article><div class="filters"><label>Intended MLB role<select id="ready-role">${options(roles, r.role)}</select></label>${bat ? `<label>Matchup<select id="ready-hand"><option value="vsr" ${r.hand === "vsr" ? "selected" : ""}>vs right-handers</option><option value="vsl" ${r.hand === "vsl" ? "selected" : ""}>vs left-handers</option></select></label>` : ""}</div>${panel(
    "The job he could earn",
    `<p class="assessment">${esc(r.role_read)}</p>${table(
      ["MLB incumbent", "Current tools", "Potential", "Comparison"],
      r.incumbents.map(
        (i) =>
          `<tr><td>${esc(i.player.name)}${i.slot ? " · slot " + i.slot : ""}${i.locked ? " · GM locked" : ""}</td><td>${fmt(i.current, 1)}</td><td>${fmt(i.potential, 1)}</td><td>${fmt(i.current_difference, 1)} candidate advantage${i.platoon_difference != null ? "<br>" + fmt(i.platoon_difference, 1) + " matchup advantage · incumbent defense " + fmt(i.defense) : ""}</td></tr>`,
      ),
    )}${bat ? note("Candidate defense at " + r.role + ": " + fmt(r.defense) + "/10 · speed " + fmt(p.speed) + "/10. Check positional experience and usage before changing roles.") : ""}${note("Tool differences describe ratings, not projected wins. Assignments are inferred from healthy MLB players. Locks remain binding.")}`,
  )}${panel(
    "What supports the assessment",
    table(
      ["Skill", "Now / upside", "MLB role percentile", "All MLB percentile"],
      r.skills.map(
        (s) =>
          `<tr><td title="${esc(s.explanation)}">${esc(s.label)}</td><td>${fmt(s.value)} / ${fmt(s.potential)}</td><td>${fmt(s.position.percentile)} <small>n=${s.position.n}</small></td><td>${fmt(s.league.percentile)} <small>n=${s.league.n}</small></td></tr>`,
      ),
    ) +
      r.skills
        .slice(0, 3)
        .map((s) => `<p class="evidence">${esc(s.explanation)}</p>`)
        .join("") +
      (bat
        ? ""
        : note(
            "Stamina " +
              fmt(r.stamina) +
              "/10 · " +
              r.qualifying_pitches +
              " currently rated pitches at 4+; starting suitability is reviewed separately.",
          )),
  )}${panel(
    "Performance at his actual level",
    stats.length
      ? table(
          bat
            ? ["Season / league", "PA", "AVG / OBP / SLG", "OPS", "League OPS", "League rank"]
            : ["Season / league", "IP", "ERA / FIP", "K% / BB%", "League FIP", "League rank"],
          stats.map(
            (s) =>
              `<tr><td>${s.year} ${esc(s.league)}<small>${esc(levels[s.level] || "Level " + s.level)}${r.evidence?.year === s.year && r.evidence?.league_id === s.league_id ? " · review sample" : ""}</small></td>${bat ? `<td>${fmt(s.pa)}</td><td>${rate(s.avg)} / ${rate(s.obp)} / ${rate(s.slg)}</td><td>${rate(s.ops)}</td><td>${rate(s.league_metrics.ops)}</td>` : `<td>${esc(s.ip_display)}</td><td>${fmt(s.era, 2)} / ${fmt(s.fip, 2)}</td><td>${pct(s.k_pct)} / ${pct(s.bb_pct)}</td><td>${fmt(s.league_metrics.fip, 2)}</td>`}<td>${s.quality_percentile == null ? "Small sample" : fmt(s.quality_percentile) + "th percentile"}<small>${s.comparison_n} qualified peers</small></td></tr>`,
          ),
        ) +
          note(
            "Recent means this season or last season. Performance ranks require 100 PA or 30 IP. Minor-league stats remain minor-league stats; no MLB translation is assumed.",
          )
      : empty("No recorded playing time in the last three completed seasons or this season."),
  )}${panel(
    "Park, schedule and team fit",
    `<p><strong>${esc(r.fit.home)}</strong> · ${esc(r.fit.label)}</p>` +
      r.fit.notes.map((n) => `<p>${esc(n)}</p>`).join("") +
      table(
        ["Schedule-weighted factor", "Value"],
        Object.entries(r.fit.weighted).map(
          ([k, v]) =>
            `<tr><td>${esc({ avg: "Average", avg_l: "Average · left-handed", avg_r: "Average · right-handed", d: "Doubles", t: "Triples", hr: "Home runs", hr_l: "Home runs · left-handed", hr_r: "Home runs · right-handed" }[k] || k)}</td><td>${fmt(v, 3)}</td></tr>`,
        ),
      ) +
      note("This fit uses " + r.organization + " as the destination organization."),
  )}${panel(
    "Before making the move",
    r.promotion.notes.map((n) => `<p>${esc(n)}</p>`).join("") +
      table(
        ["40-man", "MLB service", "Service this year", "Options used"],
        [
          `<tr><td>${r.promotion.secondary ? "Already listed" : "Needs review / place"}</td><td>${fmt(r.promotion.service_years)} years · ${fmt(r.promotion.service_days)} days</td><td>${fmt(r.promotion.days_this_year)} days</td><td>${fmt(r.promotion.options_used)}<small>Remaining options require OOTP confirmation</small></td></tr>`,
        ],
      ) +
      `<details><summary>Contract information</summary><p>${p.salary_known ? money(p.salary) : "Salary not exported"}${p.end_year ? " · through " + p.end_year + " · " + p.years_left + " seasons" : ""}</p>${
        r.contract.length
          ? table(
              ["Year", "Salary", "Terms", "Buyout"],
              r.contract.map(
                (c) =>
                  `<tr><td>${c.year}</td><td>${money(c.salary)}</td><td>${esc(c.type || "Scheduled")}<small>${esc(c.source)}</small></td><td>${money(c.buyout)}</td></tr>`,
              ),
            )
          : note(
              "No year-by-year signed contract was exported. Confirm renewal and team control in OOTP.",
            )
      }</details>`,
  )}<details class="panel"><summary>How this review is made</summary><div class="panelbody">${r.method.map((n) => `<p>${esc(n)}</p>`).join("")}</div></details>`;
}

async function showReadiness(id, team, role = "", hand = "vsr") {
  RD.player = { id, team };
  RD.role = role;
  RD.hand = hand;
  const target = $("#ready-review");
  target.innerHTML =
    '<div class="loading">Reviewing current tools, actual stats and MLB openings…</div>';
  try {
    const r = await api("/api/office/readiness", { id, team, position: role, hand });
    if (!target.isConnected || RD.player.id !== id) return;
    target.innerHTML = readinessReport(r);
    organizeReadiness(target);
    target.scrollIntoView({ block: "start", behavior: "smooth" });
    $("#ready-role").onchange = (e) => showReadiness(id, team, e.target.value, RD.hand);
    if ($("#ready-hand"))
      $("#ready-hand").onchange = (e) =>
        showReadiness(id, team, $("#ready-role").value, e.target.value);
  } catch (e) {
    target.innerHTML = note(e.message, true);
  }
}

const bindBeforeReadiness = bindPage;

bindPage = function () {
  bindBeforeReadiness();
  if (!$("#ready-team")) return;
  $("#ready-team").onchange = (e) => {
    RD.team = Number(e.target.value);
    RD.offset = 0;
    RD.player = null;
    render();
  };
  $("#ready-search").onchange = (e) => {
    RD.q = e.target.value;
    RD.offset = 0;
    render();
  };
  $("#ready-minor").onchange = (e) => {
    RD.minor = e.target.checked;
    RD.offset = 0;
    render();
  };
  $("#ready-prev").onclick = () => {
    RD.offset = Math.max(0, RD.offset - 12);
    render();
  };
  $("#ready-next").onclick = () => {
    RD.offset += 12;
    render();
  };
  $$("[data-ready]").forEach(
    (el) => (el.onclick = () => showReadiness(Number(el.dataset.ready), Number(el.dataset.org))),
  );
  if (RD.player) showReadiness(RD.player.id, RD.player.team, RD.role, RD.hand);
};

function organizeReadiness(target) {
  const groups = {
    "The job he could earn": "Role & replacement",
    "What supports the assessment": "Ratings & stats",
    "Performance at his actual level": "Ratings & stats",
    "Park, schedule and team fit": "Team fit",
    "Before making the move": "Call-up costs",
  };
  const panels = $$(":scope > section.panel", target);
  const labels = ["Role & replacement", "Ratings & stats", "Team fit", "Call-up costs"];
  const nav = document.createElement("div");
  nav.className = "tabs readiness-tabs";
  nav.setAttribute("aria-label", "Readiness review sections");
  for (const label of labels) {
    const button = document.createElement("button");
    button.textContent = label;
    button.type = "button";
    button.onclick = () => activate(label);
    nav.appendChild(button);
  }
  target.querySelector(".filters").after(nav);
  function activate(label) {
    for (const p of panels) p.hidden = groups[p.querySelector("h2").textContent] !== label;
    for (const b of nav.children) b.classList.toggle("selected", b.textContent === label);
  }
  activate(labels[0]);
}
