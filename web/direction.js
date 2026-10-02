"use strict";
let directionTab = "Build around";
async function direction() {
  const r = await api("/api/office/direction");
  S.direction = r;
  return (
    head(
      "Who anchors our next chapter?",
      "Keep the foundation, develop the future, and explore trades only when the return improves our plan.",
      "CORE & TRADE PLAN",
    ) +
    `<div class="direction-window">${badge("This season: " + r.now)} ${badge("Next season: " + r.next)} <button data-nav="blueprint">Change the team plan</button></div>${tabs(["Build around", "Explore trades", "GM protected"], directionTab, "data-direction-tab")}<div id="direction-list">${directionRows(r)}</div>${panel("How these recommendations are made", `<details><summary>Evidence, thresholds and limitations</summary>${r.method.map((n) => `<p>${esc(n)}</p>`).join("")}</details>`)}`
  );
}
function directionRows(r) {
  const list =
    directionTab === "Build around"
      ? r.core
      : directionTab === "Explore trades"
        ? r.trade
        : r.protected;
  const intro =
    directionTab === "Build around"
      ? "Current foundations, future cornerstones and shorter-window pillars have different jobs. Potential does not establish MLB readiness."
      : directionTab === "Explore trades"
        ? "These are conditional trade discussions. Each deal needs a worthwhile return, a replacement plan and respect for your standing locks."
        : "These players retain your explicit trade protection. No recommendation removes a lock.";
  return (
    note(intro) +
    (list.length
      ? `<div class="direction-grid">${list
          .map((x) => {
            const p = x.player;
            return panel(
              p.name,
              `<div class="direction-meta">${badge(x.category, x.category === "Development cornerstone" ? "gold" : "")} ${badge(x.role)}<small>Age ${p.age} · ${fmt(x.current)}/10 current · ${fmt(x.potential)}/10 potential · ${salary(p)}</small></div><h3>${esc(x.verdict)}</h3><p class="assessment">${esc(x.condition)}</p><p>${esc(p.summary)}</p>${x.warnings.map((n) => note(n, true)).join("")}<details><summary>Age, performance, contract & positional evidence</summary>${x.facts.map((n) => `<p>${esc(n)}</p>`).join("")}${
                x.depth.length
                  ? table(
                      ["Other active role options", "Current tools"],
                      x.depth.map(
                        (q) => `<tr><td>${link(q)}</td><td>${fmt(q.current_tools, 1)}/10</td></tr>`,
                      ),
                    )
                  : ""
              }</details><div class="actions"><button data-player="${p.id}">Full player report</button><button data-watch="${p.id}">Watch</button>${x.category === "Development cornerstone" ? '<button data-nav="readiness">Review MLB readiness</button>' : ""}</div>`,
            );
          })
          .join("")}</div>`
      : empty(
          directionTab === "Explore trades"
            ? "No player currently meets this conservative trade screen. Holding can be the right decision for the saved window."
            : "No players meet this screen in the current export.",
        ))
  );
}
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-direction-tab]");
  if (!el) return;
  directionTab = el.dataset.directionTab;
  render();
});
