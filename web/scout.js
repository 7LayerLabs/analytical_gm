"use strict";
// Scout & fit (top of the Scouting page) and the Ask Jev widgets used across the app.

function scoutPanel() {
  return panel(
    "Scout & fit",
    `<p>Pick one or more players from anywhere: our system, other clubs, free agents. You'll get a scouting report on each and how he'd fit here.</p><div class="formgrid"><label class="wide">Players to scout<input name="scout"></label></div><div class="actions"><button id="scout-go" class="primary">Scout them</button></div><p id="scout-error" class="case-inline-error" role="alert" hidden></p><div id="scout-results"></div>`,
  );
}

const MINORS = /^(AAA|AA|A-ball|Rookie)/;

function scoutResults(reports) {
  const compare =
    reports.length > 1
      ? panel(
          "Side by side",
          table(
            ["Player", "This year", "Wins / season", "Our park", "Role for us", "Cost / value"],
            reports.map(
              (r) =>
                `<tr><td>${link(r)}<small>${esc(r.position)} · age ${r.age} · ${esc(r.where)}</small></td><td>${esc(r.this_year)}</td><td class="num">${fmt(r.wins, 1)}</td><td>${esc(r.park.verdict)}</td><td>${esc(r.fit.role)}</td><td>${worth(r.money.value)}<small>${esc(r.money.label)}</small></td></tr>`,
            ),
          ),
        )
      : "";
  const ask = `<div class="jev-ask"><label>Ask Jev about ${reports.length > 1 ? "these players" : "this player"}<input id="jev-question" maxlength="400" placeholder="${reports.length > 1 ? "e.g. Who is the better fit for us at second base?" : "e.g. Would he help us more than our current second baseman?"}"></label><button type="button" data-jev-free="${esc(JSON.stringify(reports.map((r) => r.id)))}">🔒 Ask Jev</button><small>Uses TypeSafe credits. Answers are saved for this export.</small><div class="jev-out"></div></div>`;
  return compare + reports.map(scoutCard).join("") + panel("Ask Jev", ask);
}

function scoutCard(r) {
  const tools = r.tools
    .map(
      (t) =>
        `<li><span>${esc(t.tool)}</span><meter min="0" max="10" value="${t.now}"></meter><b>${t.now}${t.ceiling && t.ceiling > t.now ? `<small> → ${t.ceiling}</small>` : ""}</b></li>`,
    )
    .join("");
  const history = r.history
    .map((h) => `<li><b>${h.year} ${esc(h.level)}</b> ${esc(h.line)}</li>`)
    .join("");
  const prospect = MINORS.test(r.where);
  return `<article class="panel scout-card"><header><h3>${link(r)}</h3><small>${esc(r.position)} · ${esc(r.bats_throws)} · age ${r.age} · ${esc(r.where)}${r.injured ? " · hurt" : r.day_to_day ? " · day-to-day" : ""}</small></header>
    <p class="scout-verdict">${esc(r.verdict)}</p>
    <p>${esc(r.summary)}</p>
    <div class="scout-grid"><div><h4>Tools (now → ceiling)</h4><ul class="tool-list">${tools}</ul></div><div><h4>This year</h4><p>${esc(r.this_year)}</p>${history ? `<h4>Recent seasons</h4><ul class="scout-history">${history}</ul>` : ""}</div></div>
    <dl class="scout-facts"><dt>Development</dt><dd>${esc(r.development.stage)}. ${esc(r.development.path)}</dd><dt>${esc(r.park.name)}</dt><dd><b>${esc(r.park.verdict)}</b>. ${esc(r.park.note)}</dd><dt>Fit</dt><dd><b>${esc(r.fit.role)}</b>. ${esc(r.fit.line)}</dd><dt>Money</dt><dd>${esc(r.money.line)}</dd></dl>
    <div class="actions">${jevButton("fit", { id: r.id }, "Ask Jev how he fits us")}${prospect ? jevButton("prospect", { id: r.id }, `Ask Jev: is ${r.name}'s run real?`) : ""}</div>
  </article>`;
}

// ---- Ask Jev: locked until you ask, because each question spends TypeSafe credits -----------

function jevButton(topic, payload, label) {
  return `<span class="jev-slot"><button type="button" class="jev-button" data-jev="${esc(topic)}" data-jev-payload="${esc(JSON.stringify(payload))}">🔒 ${esc(label)}</button><small>Uses TypeSafe credits</small><span class="jev-out"></span></span>`;
}

function jevReads(r) {
  return `<div class="jev-reads"><span class="eyebrow">Jev${r.cached ? " · saved answer, no charge" : ""}</span>${r.reads
    .map(
      (x) =>
        `<div class="jev-read${x.agrees === false ? " disagree" : x.agrees ? " agree" : ""}"><span>${esc(x.question)}</span><strong>${esc(x.answer)}</strong>${x.detail ? `<small>${esc(x.detail)}</small>` : ""}<meter min="0" max="1" value="${x.confidence}" title="Jev's confidence"></meter><small>${Math.round(x.confidence * 100)}% confident</small></div>`,
    )
    .join("")}<small class="jev-note">${esc(r.note)}</small></div>`;
}

async function askJev(button, topic, payload, keep = false) {
  const slot = button.parentElement,
    out = slot.querySelector(".jev-out"),
    label = button.textContent;
  button.disabled = true;
  button.textContent = "Asking Jev…";
  try {
    const r = await api("/api/jev/ask", {}, { topic, ...payload });
    out.innerHTML = jevReads(r);
    if (keep) {
      button.disabled = false;
      button.textContent = label;
    } else {
      button.remove();
      slot.querySelector(":scope > small")?.remove();
    }
  } catch (e) {
    out.innerHTML = note(e.message, true);
    button.disabled = false;
    button.textContent = "🔒 Try Jev again";
  }
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-jev], [data-jev-free]");
  if (!b || b.disabled) return;
  if (b.dataset.jev) {
    askJev(b, b.dataset.jev, JSON.parse(b.dataset.jevPayload || "{}"));
    return;
  }
  const question = b.parentElement.querySelector("#jev-question")?.value.trim();
  if (!question) {
    b.parentElement.querySelector(".jev-out").innerHTML = note(
      "Type a question for Jev first.",
      true,
    );
    return;
  }
  askJev(b, "question", { ids: JSON.parse(b.dataset.jevFree), question }, true);
});

const bindBeforeScout = bindPage;
bindPage = function () {
  bindBeforeScout();
  if (S.page !== "players" || !$("#scout-go")) return;
  $("#scout-go").onclick = async () => {
    const ids = String($("input[name=scout]").value || "")
      .split(",")
      .filter(Boolean);
    const error = $("#scout-error");
    error.hidden = true;
    if (!ids.length) {
      error.textContent = "Pick at least one player.";
      error.hidden = false;
      return;
    }
    $("#scout-go").disabled = true;
    $("#scout-go").textContent = "Scouting…";
    try {
      const r = await api("/api/office/scout", { ids: ids.join(",") });
      $("#scout-results").innerHTML = scoutResults(r.reports);
    } catch (e) {
      error.textContent = e.message;
      error.hidden = false;
    } finally {
      $("#scout-go").disabled = false;
      $("#scout-go").textContent = "Scout them";
    }
  };
};
