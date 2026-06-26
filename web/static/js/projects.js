// Screen 1 — from dVerse central command:
//   focus = #1 priority · Top priorities (myTasks) · Waiting on you (drafts) ·
//   the user's milestones (team progress).
import { startClock, poll, scheduleDailyReload, initPWA, el, clear } from "./common.js";

const dot = document.getElementById("dot");
startClock(document.getElementById("time"), document.getElementById("date"));
scheduleDailyReload();
initPWA();

const STATUS_LABEL = { TODO: "To do", IN_PROGRESS: "In progress", DONE: "Done", BLOCKED: "Blocked" };

function priorityPill(label) {
  const key = (label || "").toLowerCase();
  const cls = key === "high" ? "high" : key === "low" ? "low" : "normal";
  return el("span", `pill ${cls}`, label || "Normal");
}

function renderFocusState(f) {
  const box = document.getElementById("focus-state");
  if (!box) return;
  clear(box);
  if (!f || !f.state) return;
  const band = el("div", `focus-state ${f.state}`);
  const left = el("div", "fs-left");
  left.appendChild(el("span", "fs-label", f.label));
  left.appendChild(el("span", "fs-msg", f.message));
  band.appendChild(left);
  // timing hint on the right
  let hint = "";
  if (f.state === "prime" && f.minutes_left != null) hint = `${f.minutes_left} min left`;
  else if (f.next_window_in != null) hint = `deep work in ${f.next_window_in} min`;
  if (hint) band.appendChild(el("div", "fs-hint", hint));
  box.appendChild(band);
}

function render(data) {
  renderFocusState(data.focus);

  // FOCUS — the single most-urgent priority. Kicker adapts to the focus state.
  const focus = document.getElementById("focus");
  clear(focus);
  const top = (data.immediate || [])[0];
  const st = data.focus?.state;
  const kicker = st === "prime" ? "Peak focus — do this now"
    : st === "dip" || st === "winddown" ? "When you're ready"
    : "Do this next";
  if (top) {
    focus.appendChild(el("div", "focus-kicker", kicker));
    focus.appendChild(el("div", "focus-title", top.title));
    const meta = el("div", "focus-meta");
    meta.append(top.goal || "");
    if (top.milestone) meta.append(`  ›  ${top.milestone}`);
    focus.appendChild(meta);
    const pills = el("div"); pills.style.marginTop = ".7rem";
    pills.appendChild(priorityPill(top.priority_label));
    if (data.waiting?.count) pills.appendChild(el("span", "pill prog", `${data.waiting.count} waiting on you`));
    focus.appendChild(pills);
  } else {
    focus.appendChild(el("div", "focus-kicker", "All clear"));
    focus.appendChild(el("div", "focus-title", "No priorities right now 🎉"));
  }

  // TOP PRIORITIES — the rest of myTasks (the #1 is in focus above).
  const rail = document.getElementById("immediate");
  clear(rail);
  const rest = (data.immediate || []).slice(1, 4);
  if (rest.length) {
    for (const t of rest) {
      const row = el("div", "task-row");
      row.appendChild(priorityPill(t.priority_label));
      const txt = el("div");
      txt.appendChild(el("div", "ttitle", t.title));
      if (t.goal) txt.appendChild(el("div", "tgoal", t.goal));
      row.appendChild(txt);
      rail.appendChild(row);
    }
  } else {
    rail.appendChild(el("div", "empty small", "Just the one above."));
  }

  // WAITING ON YOU — drafts/approvals pending sign-off.
  const waiting = document.getElementById("waiting");
  clear(waiting);
  const w = data.waiting || {};
  if ((w.items || []).length) {
    for (const it of w.items) {
      const row = el("div", "task-row");
      row.appendChild(el("span", "pill prog", "Approve"));
      const txt = el("div");
      txt.appendChild(el("div", "ttitle", it.title));
      if (it.goal) txt.appendChild(el("div", "tgoal", it.goal));
      row.appendChild(txt);
      waiting.appendChild(row);
    }
  } else if (w.count) {
    waiting.appendChild(el("div", "waiting-count", `${w.count} item${w.count > 1 ? "s" : ""} awaiting your sign-off`));
  } else {
    waiting.appendChild(el("div", "empty small", "Nothing waiting ✓"));
  }

  // MILESTONES — team progress, one card per milestone.
  const msLabel = document.getElementById("ms-label");
  if (msLabel) msLabel.textContent = `${data.person ? data.person + "'s" : "Your"} milestones · team progress`;
  const grid = document.getElementById("milestones");
  clear(grid);
  for (const m of data.milestones || []) {
    const card = el("div", "project");
    if (m.goal) card.appendChild(el("div", "pgoal", m.goal));
    const head = el("div", "mhead");
    head.appendChild(el("div", "pname", m.title || "—"));
    if (m.total) head.appendChild(el("span", "pill prog", `${m.done}/${m.total}`));
    card.appendChild(head);

    const foot = el("div", "mfoot");
    foot.appendChild(el("span", `pill ${(m.status || "").toLowerCase() === "in_progress" ? "prog" : "normal"}`,
      STATUS_LABEL[m.status] || m.status || ""));
    card.appendChild(foot);

    const bar = el("div", "progress");
    const span = el("span");
    span.style.width = `${Math.max(2, m.pct || 0)}%`;
    bar.appendChild(span);
    card.appendChild(bar);
    grid.appendChild(card);
  }
  if (!(data.milestones || []).length) {
    grid.appendChild(el("div", "empty", "No milestones."));
  }
}

poll("/api/projects", render, dot);
