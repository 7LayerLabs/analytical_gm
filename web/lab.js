"use strict";
const labQuestions = [
  {
    type: "Replacement",
    title: "Replace an injured player",
    detail: "Compare internal depth with temporary outside help.",
  },
  {
    type: "Promotion",
    title: "Is this prospect ready?",
    detail: "Weigh current ability, playing time and roster costs.",
  },
  {
    type: "Signing",
    title: "Review a free agent",
    detail: "Check his role, park fit and cost against our alternatives.",
  },
  {
    type: "Trade",
    title: "Does this trade help us?",
    detail: "Choose the players by name and compare the package.",
  },
  {
    type: "Offers",
    title: "Compare trade offers",
    detail: "Got offers for a player on the block? Line them up and pick one.",
  },
  {
    type: "Extension",
    title: "Should we extend him?",
    detail: "Review the player, his existing contract and our window.",
  },
  {
    type: "Deadline plan",
    title: "Plan our trade deadline",
    detail: "Find pieces we can move while protecting next season.",
  },
];
lab = async function () {
  const choice = labQuestions.find((x) => x.type === S.labType),
    mode = S.office.state.blueprint.seasons[S.status.snapshot.season];
  const saved = S.office.state.decisions
    .slice(0, 10)
    .map(
      (x) =>
        `<div class="feeditem"><button data-open-case="${esc(x.id)}">${esc(x.report.question)}</button><small>${date(x.game_date)} · ${esc(x.status)}</small><select data-case-status="${esc(x.id)}" aria-label="Case status">${options(["Exploring", "Chosen", "Applied in OOTP", "Revisit"], x.status)}</select></div>`,
    )
    .join("");
  return (
    head(
      "What are we deciding?",
      "Start with a question. The department brings the evidence and alternatives.",
      "DECISION LAB",
    ) +
    `<div class="twocol"><div>${choice ? panel(choice.title, `<button type="button" id="change-case-question" class="change-question">Choose a different question</button>${simpleCaseForm(choice, mode)}`) : `<div class="case-questions">${labQuestions.map((x) => `<button type="button" data-lab-type="${x.type}"><strong>${x.title}</strong><span>${x.detail}</span></button>`).join("")}</div>`}<div id="case-report"></div></div><aside>${panel("Our plan", `<h2>${esc(mode)}</h2><p>Next season: ${esc(S.office.state.blueprint.seasons[Number(S.status.snapshot.season) + 1])}</p><small>Saved player locks apply to every comparison.</small><details><summary>See standing locks</summary>${lockList()}</details>`)}${panel("Saved cases", saved || empty("Save a review to return to it here."))}</aside></div>`
  );
};
function simpleCaseForm(choice, mode) {
  const kind = choice.type,
    trade = kind === "Trade",
    offers = kind === "Offers",
    deadline = kind === "Deadline plan",
    offer = ["Signing", "Extension"].includes(kind),
    year = S.status.snapshot.season;
  const player = trade
    ? `<div class="formgrid"><label>Who are we giving up?<input name="send"></label><label>Who would we receive?<input name="receive"></label></div>`
    : offers
      ? `<label class="case-main-label">Who's on the block?<input name="send"></label><p class="case-plan-note">Add the offers you've received: two to four. Each can be one player or a package.</p><div class="formgrid">${[1, 2, 3, 4].map((n) => `<label>Offer ${n}${n > 2 ? " (optional)" : ""}<input name="offer${n}"></label>`).join("")}</div>`
      : deadline
        ? ""
        : `<label class="case-main-label">${kind === "Replacement" ? "Who needs replacing?" : kind === "Promotion" ? "Which prospect?" : kind === "Signing" ? "Which free agent?" : "Which player?"}<input id="case-player-search" type="search" autocomplete="off" placeholder="Start typing a name" aria-label="Search case player"><input name="player_id" type="hidden"><div id="case-player-matches" aria-live="polite"></div><div id="case-selected-player"></div></label>`;
  const position =
    kind === "Replacement"
      ? `<label class="case-position">Or review a position<select name="position">${["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"].map((pos) => `<option value="${pos}">${pos === "P" ? "Starting pitcher" : roleNames[pos]}</option>`).join("")}</select></label>`
      : '<input type="hidden" name="position" value="P">';
  const defaultInputs = `<div hidden>${!trade && !offers ? '<input name="send" value=""><input name="receive" value="">' : ""}${!offer ? '<input name="annual_offer" value="0"><input name="offer_years" value="1"><input name="start_year" value="' + (year + 1) + '">' : ""}${kind !== "Promotion" ? '<input name="added_service_days" value="0">' : ""}</div>`;
  return `<form id="case-form" class="simple-case"><input type="hidden" name="type" value="${kind}">${player}${position}<p class="case-plan-note">Using our <strong>${esc(mode)}</strong> plan and saved player locks.</p><details class="case-options"><summary>More options${offer ? " · offer terms" : ""}</summary><div class="formgrid"><label class="wide">Anything the department should consider?<textarea name="question" placeholder="Optional: tell us what matters to you."></textarea></label><label>Direction for this review<select name="scenario_mode">${options(S.office.modes, mode)}</select></label>${offer ? `<label>Proposed annual salary ($)<input name="annual_offer" type="number" min="0" max="100000000" value="0"><small>Leave blank or zero for an initial review. It is not a confirmed asking price.</small></label><label>Years offered<input name="offer_years" type="number" min="1" max="15" value="1"></label>${kind === "Extension" ? `<label>First year of extension<input name="start_year" type="number" value="${year + 1}"></label>` : '<input type="hidden" name="start_year" value="' + year + '">'}` : ""}${kind === "Promotion" ? '<label>Additional service days to illustrate<input name="added_service_days" type="number" min="0" max="172" value="0"></label>' : ""}${trade || offers ? '<label class="wide"><input type="checkbox" name="override"> Compare without trade protection for this review only. Saved locks stay in place.</label>' : ""}</div></details>${defaultInputs}<p id="case-error" class="case-inline-error" role="alert" hidden></p><div class="actions"><button id="review-case" class="primary">${buttonLabel(kind)}</button><button type="button" id="save-case" disabled>Save this case</button></div></form>`;
}
function buttonLabel(kind) {
  return kind === "Trade"
    ? "Review this trade"
    : kind === "Offers"
      ? "Compare these offers"
      : kind === "Deadline plan"
        ? "Review our deadline options"
        : "Get the assistant GM's call";
}
const bindBeforeSimpleLab = bindPage;
bindPage = function () {
  bindBeforeSimpleLab();
  if (S.page !== "lab") return;
  $$("[data-lab-type]").forEach(
    (b) =>
      (b.onclick = () => {
        S.labType = b.dataset.labType;
        S.currentCase = null;
        render();
      }),
  );
  if ($("#change-case-question"))
    $("#change-case-question").onclick = () => {
      S.labType = null;
      S.currentCase = null;
      render();
    };
  $$("[data-open-case]").forEach(
    (b) =>
      (b.onclick = () => {
        const saved = S.office.state.decisions.find((x) => x.id === b.dataset.openCase);
        if (!saved) return;
        S.currentCase = null;
        if ($("#save-case")) $("#save-case").disabled = true;
        $("#case-report").innerHTML =
          note(
            "Saved review from " +
              date(saved.game_date) +
              ". This preserves the evidence at that export; start a new review for current conditions.",
          ) + caseReport(saved.report);
        $("#case-report").scrollIntoView({ behavior: "smooth", block: "start" });
      }),
  );
  const form = $("#case-form");
  if (!form) return;
  let revision = 0;
  function invalidate() {
    revision++;
    S.currentCase = null;
    $("#save-case").disabled = true;
    $("#case-report").innerHTML = "";
  }
  form.addEventListener("input", invalidate);
  form.addEventListener("change", invalidate);
  form.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b?.dataset.packagePlayer || b?.dataset.packageRemove) invalidate();
  });
  const search = $("#case-player-search");
  let generation = 0;
  if (search)
    search.oninput = async () => {
      const gen = ++generation,
        q = search.value.trim();
      form.elements.player_id.value = "";
      $("#case-selected-player").innerHTML = "";
      $("#case-player-matches").innerHTML = "";
      if (q.length < 2) return;
      try {
        const result = await api("/api/office/players", {
          scope: S.labType === "Signing" ? "free" : "organization",
          q,
          limit: 8,
        });
        if (gen !== generation || !form.isConnected) return;
        $("#case-player-matches").innerHTML = result.players.length
          ? result.players
              .map(
                (p) =>
                  `<button type="button" data-case-pick="${p.id}"><strong>${esc(p.name)}</strong><small>${p.position} · ${esc(p.team)}${p.injured || p.on_dl ? " · Injury review" : ""}</small></button>`,
              )
              .join("")
          : "<p>No matching players. Try another name.</p>";
        $$("[data-case-pick]").forEach(
          (b) =>
            (b.onclick = () => {
              const p = result.players.find((x) => x.id === Number(b.dataset.casePick));
              invalidate();
              ++generation;
              form.elements.player_id.value = p.id;
              form.elements.position.value = p.kind === "pit" ? "P" : p.position;
              search.value = p.name;
              $("#case-player-matches").innerHTML = "";
              $("#case-selected-player").innerHTML =
                `<span class="selected-case-player">${esc(p.name)} · ${p.position} <button type="button" id="clear-case-player" aria-label="Clear selected player">×</button></span>`;
              $("#clear-case-player").onclick = () => {
                invalidate();
                form.elements.player_id.value = "";
                search.value = "";
                $("#case-selected-player").innerHTML = "";
                search.focus();
              };
            }),
        );
      } catch (e) {
        if (gen === generation) $("#case-player-matches").innerHTML = `<p>${esc(e.message)}</p>`;
      }
    };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(form),
      c = Object.fromEntries(f),
      error = $("#case-error"),
      button = $("#review-case");
    error.hidden = true;
    c.player_id = Number(c.player_id || 0);
    c.override = f.has("override");
    const ids = (v) =>
      String(v || "")
        .split(",")
        .filter(Boolean)
        .map(Number);
    for (const k of ["send", "receive"]) c[k] = ids(c[k]);
    if (c.type === "Offers") {
      c.offers = [1, 2, 3, 4]
        .map((n) => ({ receive: ids(c["offer" + n]) }))
        .filter((o) => o.receive.length);
      [1, 2, 3, 4].forEach((n) => delete c["offer" + n]);
    }
    const failure =
      ["Promotion", "Signing", "Extension"].includes(c.type) && !c.player_id
        ? "Choose a player from the name-search results."
        : c.type === "Trade" && (!c.send.length || !c.receive.length)
          ? "Choose at least one outgoing and one incoming player."
          : c.type === "Offers" && (!c.send.length || c.offers.length < 2)
            ? "Choose who's on the block and at least two offers."
            : null;
    if (failure) {
      error.textContent = failure;
      error.hidden = false;
      return;
    }
    if (!c.question && c.type !== "Offers")
      c.question =
        c.type === "Replacement"
          ? c.player_id
            ? "Who should replace " + search.value + "?"
            : "Who can cover " + (c.position === "P" ? "a starting-pitcher spot" : c.position) + "?"
          : c.type === "Promotion"
            ? "Is " + search.value + " ready to help us now?"
            : c.type === "Signing"
              ? "Would " + search.value + " help our club?"
              : c.type === "Extension"
                ? "Should we extend " + search.value + "?"
                : c.type === "Trade"
                  ? "Does this trade improve our team?"
                  : "How should we approach the trade deadline?";
    const submittedRevision = revision;
    button.disabled = true;
    button.textContent = "Reviewing…";
    $("#save-case").disabled = true;
    try {
      const report = await api("/api/office/evaluate", {}, c);
      if (revision !== submittedRevision || !form.isConnected) return;
      S.currentCase = c;
      $("#case-report").innerHTML = caseReport(report);
      $("#save-case").disabled = false;
      $("#case-report").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      error.textContent = e.message;
      error.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = buttonLabel(c.type);
    }
  };
};
