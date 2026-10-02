"use strict";
// The assistant GM's call card for every Decision Lab question that has one.
const caseReportBeforeTrade = caseReport;
caseReport = function (r) {
  if (r.type === "Offers") return offersReport(r);
  if (r.trade_review) return tradeReport(r);
  if (r.call) return callCard(r) + seeTheNumbers(caseReportBeforeTrade(r));
  return (
    (r.type === "Trade"
      ? note(
          "This saved trade report uses the earlier format. Run a new review for a current verdict and roster comparison.",
          true,
        )
      : "") + caseReportBeforeTrade(r)
  );
};
const seeTheNumbers = (html) =>
  `<details class="see-numbers"><summary>See the numbers: the analytics department's full review</summary>${html}</details>`;
// The assistant GM's call leads; the analytics department's full review folds underneath.
function tradeReport(r) {
  if (!r.call) return legacyVerdict(r) + analyticsReview(r);
  return callCard(r) + seeTheNumbers(analyticsReview(r));
}

const CALL_STYLE = { "Do it": "go", "Do it if...": "maybe", "Don't": "no", "Hang up": "stop" };

// $151M, $5.2M, $740K, -$5.0M (matches value.dollars on the server)
function worth(n) {
  const sign = n < 0 ? "-" : "",
    a = Math.abs(n || 0);
  if (a >= 1e7) return `${sign}$${Math.round(a / 1e6)}M`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  return `${sign}$${Math.round(a / 1e3)}K`;
}

function callCard(r) {
  const c = r.call;
  const items = (xs, none) =>
    xs.length ? `<ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p>${esc(none)}</p>`;
  const below = (label) =>
    label === "We give"
      ? "Less than nothing: a contract we're better off without."
      : "Less than nothing: we'd be taking on a bad contract.";
  const side = ({ label, total, players = [], note = "" }) =>
    `<div class="ledger-side"><span class="eyebrow">${esc(label)}</span><strong>${worth(total)}</strong>${total < 0 ? `<small>${below(label)}</small>` : note ? `<small>${esc(note)}</small>` : ""}<ul>${players
      .map((p) => `<li>${link(p)}<b>${worth(p.value)}</b></li>`)
      .join("")}</ul></div>`;
  const ledger = c.ledger?.length
    ? c.ledger
    : c.give_players
      ? [
          { label: "We give", total: c.give, players: c.give_players },
          { label: "We get", total: c.get, players: c.get_players },
        ]
      : [];
  return `<section class="panel call-card call-${CALL_STYLE[c.call] || "maybe"}">
    <div class="call-top"><span class="eyebrow">Assistant GM · ${esc(c.mode)} · ${date(r.game_date)}</span>
      <h2 class="call-word">${esc(c.call)} <small>${c.strength === "strong" ? "Strong call" : "Lean"}</small></h2>
      <p class="call-headline">${esc(c.headline)}</p></div>
    ${ledger.length ? `<div class="ledger">${ledger.map(side).join("")}</div>` : ""}
    <div class="procon"><div><h3>Why it helps</h3>${items(c.pros, "Nothing.")}</div><div><h3>What it costs us</h3>${items(c.cons, "Nothing that matters.")}</div></div>
    ${c.roster?.length ? `<div class="call-roster"><h3>On the field</h3>${items(c.roster, "")}</div>` : ""}
    ${c.make_it_work ? `<p class="make-it-work"><strong>What would make it work:</strong> ${esc(c.make_it_work)}</p>` : ""}
    <small class="call-foot">Value = projected wins × ${worth(c.price_of_a_win)} a win (what this league pays) − salary, over the years we control each player. Make the move in OOTP.</small>
  </section>`;
}

// Several offers for the same player(s): one verdict, a ranked table, then each offer's full card.
function offersReport(r) {
  const v = r.verdict;
  const salary = (c) =>
    !c.salary_change
      ? "No change"
      : c.salary_change < 0
        ? `Saves ${worth(-c.salary_change)}`
        : `Adds ${worth(c.salary_change)}`;
  const rows = r.offers.map(
    (o, i) =>
      `<tr class="${i === 0 ? "offer-best" : ""}"><td>${i + 1}</td><td><strong>${esc(o.label)}</strong><small>${o.call.get_players.map((p) => esc(p.name)).join(", ")}</small></td><td><span class="call-chip call-${CALL_STYLE[o.call.call] || "maybe"}">${esc(o.call.call)}</span></td><td>${worth(o.call.get)}</td><td>${o.call.wins_now > 0 ? "+" : ""}${fmt(o.call.wins_now, 1)}</td><td>${salary(o.call)}</td><td>${o.tags.map((t) => `<span class="offer-tag">${esc(t)}</span>`).join("")}</td></tr>`,
  );
  const detail = (o, i) =>
    `<details class="offer-detail"><summary>${i + 1}. ${esc(o.label)}: ${esc(o.call.call)}${o.call.call.endsWith("...") ? "" : "."} ${esc(o.call.headline)}</summary>${callCard({ call: o.call, game_date: r.game_date })}${seeTheNumbers(analyticsReview({ trade_review: o.trade_review, call: o.call, checks: [], package: { flags: [] } }))}</details>`;
  return (
    `<section class="panel call-card call-${CALL_STYLE[v.call] || "maybe"}">
      <div class="call-top"><span class="eyebrow">Assistant GM · ${esc(r.scenario_mode)} · ${date(r.game_date)} · On the block: ${r.on_the_block.map((p) => esc(p.name)).join(", ")} (${worth(r.give)})</span>
        <h2 class="call-word offers-word">${esc(v.headline)}</h2></div>
      <ul class="offer-reasons">${v.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      ${table(["#", "Offer", "Call", "Value we get", "Wins this year", "Salary", ""], rows)}
      <small class="call-foot">Ranked by value to us, with extra weight on this season's wins while contending. Open any offer for the full read.</small>
    </section>` + r.offers.map(detail).join("")
  );
}

// Saved before the assistant GM existed: show the old heuristic verdict as it was.
function legacyVerdict(r) {
  const t = r.trade_review;
  return panel(
    "The department’s call",
    `<span class="eyebrow">${esc(r.scenario_mode)} · ${date(r.game_date)}</span><h2>${esc(t.verdict)}</h2><p class="trade-lead">${esc(t.lead)}</p><ul class="trade-reasons">${t.reasons.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`,
  );
}

function analyticsReview(r) {
  const t = r.trade_review;
  return (
    panel(
      "What actually changes on the roster?",
      `<p>Compare keeping the players with making this trade. Current assignments use the latest injury flags; the recovery scenario removes injuries only for players in this package.</p>${t.comparisons
        .map(
          (c) =>
            `<details ${c.hand === "vsr" ? "open" : ""}><summary>${c.hand === "vsr" ? "Against right-handed pitching" : "Against left-handed pitching"}</summary>${
              c.changes.length
                ? table(
                    ["Role", "Keep the roster", "After the trade"],
                    c.changes.map(
                      (x) =>
                        `<tr><td>${esc(x.role)}</td><td>${x.before ? link(x.before) : "Unfilled"}</td><td>${x.after ? link(x.after) : "Unfilled"}</td></tr>`,
                    ),
                  )
                : empty("No selected assignments change.")
            }<small>Average selected-player preference change: ${c.current_change > 0 ? "+" : ""}${fmt(c.current_change, 2)} now; ${c.recovery_change > 0 ? "+" : ""}${fmt(c.recovery_change, 2)} in the recovery scenario. These are grade comparisons, not projected wins.</small></details>`,
        )
        .join("")}`,
    ) +
    panel(
      "The talent we receive—and the talent we lose",
      `<div class="direction-grid">${t.people
        .map(
          (x) =>
            `<article class="trade-player"><span class="eyebrow">${esc(x.side)}</span><h3>${link(x.player)}</h3><small>${x.player.position} · age ${x.player.age}${x.player.injured ? " · injured" : ""}</small><p><strong>${esc(x.assessment)}</strong></p><p>${x.side === "Incoming" ? `Proposed job: ${esc(x.jobs.length ? x.jobs.join("; ") : "Not selected ahead of our current options; no demonstrated MLB role.")}` : "Giving up this player removes his future contribution as well as his present availability."}</p><p>${esc(x.control)}</p>${x.observed_year && x.observed ? `<p>${x.observed_year} observed MLB performance: ${x.player.kind === "bat" ? `${fmt(x.observed.pa)} PA · ${rate(x.observed.obp)} OBP · ${rate(x.observed.ops)} OPS · ${fmt(x.observed.hr)} HR` : `${esc(x.observed.ip_display || "")} IP · ${fmt(x.observed.era, 2)} ERA · ${fmt(x.observed.fip, 2)} FIP`}<small>Recorded results in his own park/schedule; separate from the forecast.</small></p>` : ""}<details><summary>Current ability, upside, performance & park fit</summary><p>Overall current ${fmt(x.current)}/10 · potential ${fmt(x.potential)}/10. Potential describes upside, not guaranteed performance.</p>${table(
              ["Tool", "Current rating"],
              Object.entries(x.tools).map(
                ([k, v]) => `<tr><td>${esc(k)}</td><td>${fmt(v)}/10</td></tr>`,
              ),
            )}<p>${esc(x.player.summary)}</p>${x.park.map((n) => `<p>${esc(n)}</p>`).join("")}<button data-player="${x.player.id}">Full player report</button></details></article>`,
        )
        .join("")}</div>`,
    ) +
    panel(
      "Money: what is known, and what is missing",
      `<p>These are signed commitments shown in the export. <strong>Missing future salaries are not savings.</strong> Players may remain under team control and receive renewal or arbitration salaries.</p><details><summary>Year-by-year signed commitments</summary>${table(
        ["Season", "Known commitment change", "Incomplete salary information"],
        t.financial.map(
          (x) =>
            `<tr><td>${x.year}</td><td>${x.known_change < 0 ? "Reduction of " + money(-x.known_change) : "Increase of " + money(x.known_change)}<small>${x.complete ? "Scheduled comparison" : "Partial comparison; not net savings"}</small></td><td>${esc(x.unknown.length ? x.unknown.join(", ") + ": future salary unknown" : "Both sides have exported salaries")}</td></tr>`,
        ),
      )}<p>Current-year figures are full-season scheduled amounts; retained salary and proration are not modeled.</p></details>`,
    ) +
    ownerTradeScorecard(t.owner_impact) +
    panel(
      r.call ? "Transaction checks" : "What would change our answer?",
      `${r.call ? "" : "<p>" + (t.verdict === "Decline this trade" ? "A return that replaces the core talent we lose, fills a more important role, or clearly changes the roster comparison. Salary relief alone does not establish that case." : "A clearer role upgrade, confirmed salary terms and legal roster assignments could make the decision stronger.") + "</p>"}<details><summary>Transaction checks & method</summary><ul>${[...r.checks, ...t.checks, ...r.package.flags].map((n) => `<li>${esc(n)}</li>`).join("")}</ul><p>${esc(t.method)}</p></details><small>This is the department’s recommendation on the proposed exchange. OOTP acceptance and transaction eligibility are separate checks; saving does not move players.</small>`,
    )
  );
}

function ownerTradeScorecard(goals) {
  if (!goals?.length) return panel("Owner-goal impact", empty("No active owner goals saved."));
  const count = (color) => goals.filter((g) => g.signal === color).length;
  return panel(
    "Owner-goal impact",
    `<div class="owner-impact-summary"><span class="owner-impact-chip green">${count("green")} supported</span><span class="owner-impact-chip red">${count("red")} opposed / unaddressed</span><span class="owner-impact-chip amber">${goals.filter((g) => !g.signal || g.signal === "amber").length} uncertain</span></div><p class="owner-impact-key">Green: helps the goal. Red: works against it or shows no progress. Amber: mixed or unverified. These are package assessments, not owner-confirmed completion.</p><div class="owner-impact-grid">${goals
      .map((g) => {
        const color = ["green", "red", "amber"].includes(g.signal) ? g.signal : "amber";
        return `<article class="owner-impact-card ${color}"><div class="owner-impact-status">${color === "green" ? "✓" : color === "red" ? "✕" : "?"} ${esc(g.label || "Re-run review for a current assessment")}</div><h3>${esc(g.goal)}</h3><p>${esc(g.read)}</p></article>`;
      })
      .join("")}</div>`,
  );
}
