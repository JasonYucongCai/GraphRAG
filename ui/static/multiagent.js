/* multiagent.js — the Multi Agent portal (strict IPP social layer).
 *
 * Top-level view (header nav): Control Center ⇄ Multi Agent.
 * Multi Agent view:
 *   LEFT sidebar  — sub-tabs [👥 Agent Stage | 🤝 Many Agents]:
 *     Agent Stage: the mini agent boxes (each agent's own reasoning);
 *                  CLICK an agent → its process opens on the right panel.
 *     Many Agents: goal naming + instructions, agent selection, start/stop
 *                  the team, instruct one agent, goal browser.
 *   RIGHT canvas  — sub-tabs [🧠 Agent Process | 💬 Inter Agent Chat |
 *                  🌐 Global Chat Board]:
 *     Agent Process: the selected agent's full live trace (thinking, tool
 *                  calls, tool results, messages).
 *     Inter Agent Chat: board posts authored by the 20 agents, rendered
 *                  with addressing  Alice [Alice -> Bob] …
 *     Global Chat Board: ALL board posts (agents + user) with addressing
 *                  Alice [Alice -> chat board] / [Alice -> agents], plus a
 *                  post-as-user input.
 */
"use strict";

const ma$ = (s) => document.querySelector(s);

// ── state ────────────────────────────────────────────────────────────────
const MA = {
  agents: [],           // [{agent_id, name, status, ...}]
  boxes: new Map(),     // agent_id → mini box element
  traces: new Map(),    // agent_id → raw event entries (the full process)
  answers: new Map(),   // agent_id → accumulated final answer (full text)
  tasks: new Map(),     // agent_id → the current task/instruction text
  selectedAgent: null,  // agent_id shown in the right process panel
  events: null,         // EventSource
  cursor: 0,
  selected: new Set(),  // team checkbox selection
  agentIds: new Set(),
  currentGoalId: null,  // the goal created or resumed (send targets it)
  view: "control",      // "control" | "multiagent"
  sub: "stage",         // sidebar sub-tab
  rtab: "process",      // right panel tab
  boardTimer: null,
  boardCount: 0,
};

// ── avatar / esc / names ─────────────────────────────────────────────────
function maHue(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 360;
  return h;
}
function maAvatar(agentId, name, size) {
  const hue = maHue(agentId);
  const el = document.createElement("span");
  el.className = "ma-avatar";
  el.style.width = el.style.height = size;
  el.style.background = `hsl(${hue} 55% 42%)`;
  el.style.color = "#fff";
  el.textContent = (name || agentId).charAt(0).toUpperCase();
  return el;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function truncate(s, n) {
  s = String(s ?? "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}
function maName(id) {
  const a = MA.agents.find((x) => x.agent_id === id);
  return a ? a.name : (id === "user" ? "User" : id);
}
/** Resolve a message's addressing target to a display label. */
function maTargetLabel(toId) {
  if (!toId || toId === "chat_board") return "chat board";
  if (toId === "agents") return "agents";
  return maName(toId);
}

// ── boot ─────────────────────────────────────────────────────────────────
async function maBoot() {
  maBind();
  await maLoadAgents();
  maConnectEvents();
  await maRefreshStatus();
  maSwitchView(MA.view);
}

async function maLoadAgents() {
  try {
    const res = await fetch("/api/social/agents");
    const data = await res.json();
    MA.agents = data.agents || [];
    MA.agentIds = new Set(MA.agents.map((a) => a.agent_id));
    maRenderPick();
    maRenderBoxes();
    maRenderInstructSelect();
  } catch (e) {
    maStatus("⚠ agents load failed: " + e.message);
  }
}

// ── sidebar: Many Agents pick list (pill toggles) ────────────────────────
function maRenderPick() {
  const wrap = ma$("#ma-agent-pick");
  if (!wrap) return;
  wrap.innerHTML = "";
  MA.agents.forEach((a) => {
    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = "ma-pill";
    pill.dataset.agent = a.agent_id;
    pill.title = `${a.agent_id} — ${a.bio || ""}`;
    const check = document.createElement("span");
    check.className = "ma-pill-check";
    check.textContent = "✓";
    pill.append(check, maAvatar(a.agent_id, a.name, "16px"),
      document.createTextNode(` ${a.name}`));
    pill.addEventListener("click", () => {
      if (MA.selected.has(a.agent_id)) MA.selected.delete(a.agent_id);
      else MA.selected.add(a.agent_id);
      maRenderPick();
    });
    wrap.appendChild(pill);
  });
  maUpdatePickCount();
}

function maUpdatePickCount() {
  const el = ma$("#ma-pick-count");
  if (el) {
    el.textContent = MA.selected.size
      ? `${MA.selected.size} selected`
      : "all agents (empty = all)";
  }
  document.querySelectorAll("#ma-agent-pick .ma-pill").forEach((p) => {
    p.classList.toggle("selected", MA.selected.has(p.dataset.agent));
  });
}

function maRenderInstructSelect() {
  const sel = ma$("#ma-instruct-agent");
  if (!sel) return;
  sel.innerHTML = "";
  MA.agents.forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a.agent_id;
    opt.textContent = `${a.name} (${a.agent_id})`;
    sel.appendChild(opt);
  });
}

// ── Agent Stage: compact one-column status cards (clickable → process) ──
function maRenderBoxes() {
  const grid = ma$("#ma-boxes");
  if (!grid) return;
  grid.innerHTML = "";
  MA.boxes.clear();
  MA.agents.forEach((a) => {
    const box = document.createElement("div");
    box.className = "ma-box" + (a.agent_id === MA.selectedAgent ? " selected" : "");
    box.dataset.agent = a.agent_id;
    box.title = "click to watch " + a.name + "'s process";
    box.innerHTML = `
      <div class="ma-box-head">
        ${maAvatar(a.agent_id, a.name, "22px").outerHTML}
        <div class="ma-box-title">
          <strong>${esc(a.name)}</strong>
          <span class="ma-box-id">${esc(a.agent_id)}</span>
        </div>
        <span class="ma-box-status ${esc(a.status || "idle")}">${esc(a.status || "idle")}</span>
      </div>
      <div class="ma-box-activity">${esc(a.last_activity || "idle — ready")}</div>`;
    box.addEventListener("click", () => maSelectAgent(a.agent_id));
    grid.appendChild(box);
    MA.boxes.set(a.agent_id, box);
  });
  maStageStats();
}

function maStageStats() {
  const st = ma$("#ma-stage-stats");
  if (!st) return;
  const running = MA.agents.filter((a) => a.status === "running").length;
  const done = MA.agents.filter((a) => a.status === "done").length;
  const error = MA.agents.filter((a) => a.status === "error").length;
  st.textContent = `${MA.agents.length} agents · ${running} running · ${done} done · ${error} error · click an agent to inspect`;
}

// ── agent selection → right process panel ────────────────────────────────
function maSelectAgent(agentId) {
  MA.selectedAgent = agentId;
  MA.boxes.forEach((box, id) => {
    box.classList.toggle("selected", id === agentId);
  });
  maSwitchRtab("process");
  maRenderProcess();
}

function maMarkdown(text) {
  const safe = esc(text || "");
  if (window.marked) {
    return `<div class="md">${marked.parse(safe, { breaks: true, gfm: true })}</div>`;
  }
  return `<div class="md"><pre>${safe}</pre></div>`;
}

function maProcessCounters(entries) {
  const c = { tools: 0, thinking: 0, messages: 0 };
  for (const e of entries) {
    if (e.type === "tool_call") c.tools++;
    else if (e.type === "thinking") c.thinking++;
    else if (e.type === "message") c.messages++;
  }
  return c;
}

/** Build the foldable process steps (ChatGPT/Copilot style).
 *  Each thinking / message / tool is its own <details> step with a
 *  timestamp; the tool step folds the call AND its result together.
 */
function maProcessSteps(entries) {
  const out = [];
  let openToolIdx = -1;   // index in `out` of the open tool step
  let turn = 0;
  const time = (e) => (e.ts || "").slice(11);
  for (const e of entries) {
    const t = e.type;
    if (t === "start") {
      out.push(`<div class="ma-proc turn"><span class="ma-proc-time">${esc(time(e))}</span>▶ turn ${++turn} started</div>`);
    } else if (t === "thinking") {
      const body = esc(e.content || "");
      out.push(`<details class="ma-step ma-think">
        <summary><span class="ma-proc-time">${esc(time(e))}</span>🧠 thinking (${body.length} chars)</summary>
        <pre class="ma-step-body">${body}</pre></details>`);
    } else if (t === "message") {
      const body = e.content || "";
      out.push(`<details class="ma-step ma-msg">
        <summary><span class="ma-proc-time">${esc(time(e))}</span>💬 message (${body.length} chars)</summary>
        <div class="ma-step-body">${maMarkdown(body)}</div></details>`);
    } else if (t === "tool_call") {
      const args = typeof e.args === "string" ? e.args : JSON.stringify(e.args || {});
      const nm = e.tool || "";
      openToolIdx = out.length;
      out.push(`<details class="ma-step ma-tool" open>
        <summary><span class="ma-proc-time">${esc(time(e))}</span>🛠 ${esc(nm)} <span class="ma-tool-args">${esc(args)}</span></summary>
        <div class="ma-step-body"></div></details>`);
    } else if (t === "tool_result") {
      const body = esc(e.content || "");
      if (openToolIdx >= 0) {
        const inner = `<div class="ma-proc-result"><span class="ma-proc-time">${esc(time(e))}</span>↩ result</div>
          <pre class="ma-result-body">${body}</pre>`;
        out[openToolIdx] = out[openToolIdx].replace(
          '<div class="ma-step-body"></div>',
          `<div class="ma-step-body">${inner}</div>`);
        openToolIdx = -1;
      } else {
        out.push(`<div class="ma-proc"><span class="ma-proc-time">${esc(time(e))}</span>↩ ${esc(truncate(e.content || "", 200))}</div>`);
      }
    } else if (t === "done") {
      out.push(`<div class="ma-proc done"><span class="ma-proc-time">${esc(time(e))}</span>✔ completed</div>`);
    } else if (t === "error") {
      out.push(`<div class="ma-proc error"><span class="ma-proc-time">${esc(time(e))}</span>✖ ${esc(e.error || e.content || "")}</div>`);
    }
    // `text` events are the final answer — accumulated separately
  }
  return out.join("");
}

function maRenderProcess() {
  const head = ma$("#ma-process-head");
  const log = ma$("#ma-process");
  if (!head || !log) return;
  if (!MA.selectedAgent) {
    head.innerHTML = '<span class="muted">click an agent on the left to watch its process…</span>';
    log.innerHTML = "";
    return;
  }
  const agent = MA.agents.find((a) => a.agent_id === MA.selectedAgent);
  const name = agent ? agent.name : MA.selectedAgent;
  head.innerHTML = `${maAvatar(MA.selectedAgent, name, "20px").outerHTML}
    <strong>${esc(name)}</strong>
    <span class="ma-box-id">${esc(MA.selectedAgent)}</span>
    <span class="ma-process-status ${esc(agent ? agent.status : "idle")}">${esc(agent ? agent.status : "idle")}</span>`;

  const entries = MA.traces.get(MA.selectedAgent) || [];
  const answer = MA.answers.get(MA.selectedAgent) || "";
  const task = MA.tasks.get(MA.selectedAgent) || "";
  if (!entries.length && !answer) {
    log.innerHTML = '<div class="muted">no activity yet — start the team or instruct this agent…</div>';
    return;
  }

  const parts = [];
  // the user's chat instruction
  if (task) {
    parts.push(`<div class="ma-proc-task">💬 you: ${esc(task)}</div>`);
  }
  // the ENTIRE agentic process — one foldable block (ChatGPT/Copilot style)
  const c = maProcessCounters(entries);
  parts.push(`<details class="ma-proc-fold" open>
    <summary>▸ Agentic process (${c.tools} tools · ${c.thinking} thinking · ${c.messages} messages)</summary>
    <div class="ma-proc-steps">${maProcessSteps(entries)}</div>
  </details>`);
  // the FINAL answer — full, untruncated, below the fold
  if (answer) {
    parts.push(`<div class="ma-final">
      <div class="ma-final-title">📄 Final answer</div>
      <div class="ma-final-body">${maMarkdown(answer)}</div>
    </div>`);
  }
  log.innerHTML = parts.join("");
  log.scrollTop = log.scrollHeight;
}

// ── live events (SSE) ────────────────────────────────────────────────────
function maConnectEvents() {
  if (MA.events) MA.events.close();
  MA.events = new EventSource(`/api/swarm/events?since=${MA.cursor}`);
  MA.events.onmessage = (msg) => {
    let ev;
    try { ev = JSON.parse(msg.data); } catch { return; }
    MA.cursor = ev.seq;
    maHandleEvent(ev);
  };
  MA.events.onerror = () => { /* transient — reconnects */ };
}

function maHandleEvent(ev) {
  const box = MA.boxes.get(ev.agent_id);
  const agent = MA.agents.find((a) => a.agent_id === ev.agent_id);
  if (agent) {
    const prev = agent.status;
    if (ev.type === "agent_started") agent.status = "running";
    else if (ev.type === "agent_done") agent.status = "done";
    else if (ev.type === "agent_error") agent.status = "error";
    if (prev !== agent.status && box) {
      const st = box.querySelector(".ma-box-status");
      st.className = "ma-box-status " + agent.status;
      st.textContent = agent.status;
    }
    maStageStats();
  }
  if (!box) return;

  // ── the agent's CURRENT activity (one compact line, no pile-up) ───────
  const activity = box.querySelector(".ma-box-activity");
  if (ev.type === "agent_started") {
    activity.textContent = "▶ " + truncate(ev.data?.text || "", 80);
    activity.classList.add("running");
  } else if (ev.type === "agent_done") {
    activity.textContent = "✔ done";
    activity.classList.remove("running");
    maStatusSoon(`✔ ${ev.agent_id} finished`);
  } else if (ev.type === "agent_error") {
    activity.textContent = "✖ " + truncate(ev.data?.error || "error", 70);
    activity.classList.remove("running");
  } else if (ev.type === "agent_event") {
    const entry = ev.data?.event || {};
    const kind = entry.type;
    if (kind === "thinking") {
      activity.textContent = "🧠 " + truncate(entry.content || "", 70);
    } else if (kind === "tool_call") {
      activity.textContent = "🛠 " + entry.tool;
    } else if (kind === "tool_result") {
      activity.textContent = "↩ " + truncate(entry.content || "result", 70);
    } else if (kind === "message") {
      activity.textContent = "💬 " + truncate(entry.content || "", 70);
    } else if (kind === "text") {
      activity.textContent = "📄 " + truncate(entry.content || "", 70);
    }
  }

  // ── per-agent trace + final answer (for the process panel) ─────────────
  if (ev.type === "agent_started") {
    // a new task: reset this agent's process and remember the instruction
    MA.traces.set(ev.agent_id, []);
    MA.answers.set(ev.agent_id, "");
    MA.tasks.set(ev.agent_id, ev.data?.text || "");
    maTracePush(ev.agent_id, { ts: ev.ts, type: "start", content: "" });
  } else if (ev.type === "agent_event") {
    const entry = ev.data?.event || {};
    maTracePush(ev.agent_id, {
      ts: ev.ts, type: entry.type, tool: entry.tool,
      args: entry.args, content: entry.content, error: entry.error,
    });
    if (entry.type === "text") {   // the final answer — accumulate fully
      const prev = MA.answers.get(ev.agent_id) || "";
      MA.answers.set(ev.agent_id, prev + (entry.content || ""));
    }
  } else if (ev.type === "agent_done") {
    maTracePush(ev.agent_id, { ts: ev.ts, type: "done", content: "" });
  } else if (ev.type === "agent_error") {
    maTracePush(ev.agent_id, { ts: ev.ts, type: "error", error: ev.data?.error || "" });
  }
}

function maTracePush(agentId, entry) {
  if (!MA.traces.has(agentId)) MA.traces.set(agentId, []);
  const trace = MA.traces.get(agentId);
  trace.push(entry);
  if (trace.length > 500) trace.splice(0, trace.length - 500);
  if (MA.selectedAgent === agentId && MA.rtab === "process") {
    // fast live append: re-render is cheap enough at agent pace
    maRenderProcess();
  }
}

// ── Inter Agent Chat + Global Chat Board (addressing-aware) ──────────────
async function maLoadBoard() {
  try {
    const res = await fetch("/api/social/board");
    const data = await res.json();
    const msgs = data.messages || [];
    if (msgs.length !== MA.boardCount) {
      MA.boardCount = msgs.length;
      maRenderInterChat(msgs);
      maRenderBoard(msgs);
    }
  } catch (e) { /* backend warming up */ }
}

function maRenderInterChat(msgs) {
  const log = ma$("#ma-inter-chat");
  if (!log) return;
  const agentMsgs = msgs.filter((m) => MA.agentIds.has(m.author_agent_id));
  log.innerHTML = agentMsgs.length
    ? agentMsgs.slice(-80).map(maBubble).join("")
    : '<div class="muted">agents haven\'t spoken yet…</div>';
  log.scrollTop = log.scrollHeight;
}

function maRenderBoard(msgs) {
  const log = ma$("#ma-board");
  if (!log) return;
  log.innerHTML = msgs.length
    ? msgs.slice(-80).map(maBubble).join("")
    : '<div class="muted">board empty…</div>';
  log.scrollTop = log.scrollHeight;
}

/** Render one board message WITH addressing:  Alice [Alice -> Bob] … */
function maBubble(m) {
  const author = m.author_agent_id;
  const name = maName(author);
  const who = MA.agentIds.has(author)
    ? `<span class="ma-chat-agent">${esc(name)}</span>`
    : `<span class="ma-chat-user">${esc(name)}</span>`;
  const target = maTargetLabel(m.to_agent_id);
  const addr = `<span class="ma-chat-addr"> [${esc(name)} -> ${esc(target)}]</span>`;
  const tags = (m.tags || []).map((t) => `<span class="ma-chat-tag">#${esc(t)}</span>`).join(" ");
  return `<div class="ma-chat-msg">
    <span class="ma-chat-time">${esc((m.ts || "").slice(11))}</span>${who}${addr}
    <span class="ma-chat-text">${esc(m.text)}</span>${tags ? `<span class="ma-chat-tags">${tags}</span>` : ""}
  </div>`;
}

async function maPostBoard() {
  const input = ma$("#ma-board-text");
  const text = input.value.trim();
  if (!text) return;
  try {
    await fetch("/api/social/board", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, to_agent_id: "chat_board" }),
    });
    input.value = "";
    MA.boardCount = 0;   // force refresh
    await maLoadBoard();
  } catch (e) { maStatus("⚠ board post failed: " + e.message); }
}

// ── view / tab switching ─────────────────────────────────────────────────
function maSwitchView(view) {
  MA.view = view;
  document.querySelectorAll(".topnav-tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
  });
  document.body.classList.toggle("ma-view", view === "multiagent");
  document.querySelectorAll("#tabs .tab").forEach((b) => {
    b.classList.toggle("hidden", view === "multiagent");
  });
  document.querySelectorAll("#sidebar .tabpane").forEach((p) => {
    p.classList.toggle("active", view === "multiagent" && p.id === "tab-multiagent");
  });
  const stage = ma$("#ma-stage");
  const controls = ma$("#canvas-controls");
  const graphCanvas = ma$("#graph-canvas");
  const vizFrame = ma$("#viz-frame");
  if (stage) stage.classList.toggle("hidden", view !== "multiagent");
  if (controls) controls.classList.toggle("hidden", view === "multiagent");
  if (graphCanvas) graphCanvas.classList.toggle("hidden", view === "multiagent");
  if (vizFrame) vizFrame.classList.toggle("hidden", view === "multiagent");
  if (view === "multiagent") {
    maLoadBoard();
    if (!MA.boardTimer) MA.boardTimer = setInterval(maLoadBoard, 4000);
    maRefreshStatus();
  } else if (MA.boardTimer) {
    clearInterval(MA.boardTimer);
    MA.boardTimer = null;
  }
}

function maSwitchSub(sub) {
  MA.sub = sub;
  document.querySelectorAll(".ma-subtab").forEach((b) => {
    b.classList.toggle("active", b.dataset.sub === sub);
  });
  document.querySelectorAll(".ma-subpane").forEach((p) => {
    p.classList.toggle("active", p.id === "ma-sub-" + sub);
  });
  if (sub === "data") maShowGoals();
  if (sub === "agents") maRefreshStartGoalSelect();
  if (sub === "settings") maLoadSettings();
}

function maSwitchRtab(tab) {
  MA.rtab = tab;
  document.querySelectorAll(".ma-rtab").forEach((b) => {
    b.classList.toggle("active", b.dataset.r === tab);
  });
  document.querySelectorAll(".ma-rpane").forEach((p) => {
    p.classList.toggle("active", p.id === "ma-r-" + tab);
  });
  if (tab === "process") maRenderProcess();
  if (tab === "inter") maLoadBoard();
  if (tab === "board") maLoadBoard();
}

// ── settings (⚙ Settings tab) ───────────────────────────────────────────
async function maLoadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json().catch(() => null);
    const s = (data && data.settings) || {};
    ma$("#ma-set-streaming").checked = !!s.llm_streaming;
    ma$("#ma-set-concurrent").value = s.max_concurrent ?? 4;
    ma$("#ma-set-responder").checked = s.social_responder !== false;
    ma$("#ma-set-replyrounds").value = s.max_reply_rounds ?? 2;
  } catch (e) { /* backend warming up */ }
}

async function maSaveSettings() {
  const settings = {
    llm_streaming: ma$("#ma-set-streaming").checked,
    max_concurrent: parseInt(ma$("#ma-set-concurrent").value, 10) || 4,
    social_responder: ma$("#ma-set-responder").checked,
    max_reply_rounds: parseInt(ma$("#ma-set-replyrounds").value, 10) || 2,
  };
  try {
    const res = await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    const data = await res.json().catch(() => null);
    const el = ma$("#ma-settings-status");
    if (data && data.ok) {
      const s = data.settings;
      el.textContent = `✔ saved: streaming=${s.llm_streaming ? "on" : "off"} · ` +
        `concurrency=${s.max_concurrent} · responder=${s.social_responder ? "on" : "off"}`;
    } else el.textContent = "⚠ " + ((data && data.error) || "save failed");
  } catch (e) { ma$("#ma-settings-status").textContent = "⚠ " + e.message; }
}

// ── status helpers ───────────────────────────────────────────────────────
function maStatus(msg) {
  const el = ma$("#ma-status");
  if (el) el.textContent = msg;
}
function maGoalStatus(msg) {
  const el = ma$("#ma-goal-status");
  if (el) el.textContent = msg;
}
let _statusTimer = null;
function maStatusSoon(msg) {
  maStatus(msg);
  clearTimeout(_statusTimer);
  _statusTimer = setTimeout(() => maStatus(""), 8000);
}

// ── actions ──────────────────────────────────────────────────────────────
// ── actions: create goal folder (Data) / start goal (Many Agents) ───────
async function maCreateGoal() {
  const title = ma$("#ma-goal-name").value.trim();
  if (!title) { maCreateStatus("⚠ goal folder name required"); return; }
  const description = ma$("#ma-goal-description").value.trim();
  try {
    const res = await fetch("/api/social/goal", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, description }),
    });
    const data = await res.json();
    if (data.ok && data.goal) {
      MA.currentGoalId = data.goal.goal_id;
      maCreateStatus(`✔ goal folder created: ${data.goal.goal_id} — start it in Many Agents`);
      maShowGoals();
      maRefreshStartGoalSelect();
    } else maCreateStatus("⚠ " + (data.error || JSON.stringify(data)));
  } catch (e) { maCreateStatus("⚠ create failed: " + e.message); }
}

function maCreateStatus(msg) {
  const el = ma$("#ma-create-status");
  if (el) el.textContent = msg;
}

async function maRefreshStartGoalSelect() {
  const sel = ma$("#ma-start-goal");
  if (!sel) return;
  try {
    const res = await fetch("/api/social/goals");
    const data = await res.json();
    const goals = data.goals || [];
    sel.innerHTML = goals.length
      ? `<option value="">— pick a goal folder —</option>` +
        goals.map((g) => `<option value="${esc(g.goal_id)}">${esc(g.title)} (${g.task_count} tasks)</option>`).join("")
      : `<option value="">— no goal folder yet —</option>`;
    if (MA.currentGoalId) sel.value = MA.currentGoalId;
  } catch (e) { /* backend warming up */ }
}

async function maStartTeam(goalId) {
  const instructions = ma$("#ma-goal-instructions").value.trim();
  if (!instructions) { maStatus("⚠ instructions required"); return; }
  const sel = ma$("#ma-start-goal");
  let gid = goalId || MA.currentGoalId || (sel ? sel.value : null);
  if (!gid) { maStatus("⚠ create a goal folder in the 📁 Data tab first"); return; }
  const goalName = sel && sel.selectedOptions.length
    ? sel.selectedOptions[0].textContent.split(" (")[0] : "";
  const agent_ids = MA.selected.size ? [...MA.selected]
    : MA.agents.map((a) => a.agent_id);
  maStatus("▶ starting the goal…");
  try {
    const res = await fetch("/api/swarm/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: goalName, instructions, agent_ids, goal_id: gid }),
    });
    const data = await res.json().catch(() => null);   // defensive
    if (!data) { maStatus("⚠ server returned an empty response — check the terminal log"); return; }
    if (data.ok) {
      MA.currentGoalId = data.goal_id;
      maStatus(`✔ started: goal=${data.goal_id} · ${data.agents.length} agents`);
      maSwitchSub("stage");          // show the action
      maRefreshStatus();
    } else maStatus("⚠ " + (data.error || JSON.stringify(data)));
  } catch (e) { maStatus("⚠ start failed: " + e.message); }
}

async function maStopTeam() {
  try {
    const res = await fetch("/api/swarm/stop", { method: "POST" });
    const data = await res.json();
    maStatus(data.ok ? "⏹ team stopped" : "⚠ " + (data.error || "stop failed"));
  } catch (e) { maStatus("⚠ stop failed: " + e.message); }
}

async function maInstruct() {
  const agent_id = ma$("#ma-instruct-agent").value;
  const instruction = ma$("#ma-instruct-text").value.trim();
  if (!instruction) { maStatus("⚠ instruction text required"); return; }
  try {
    const res = await fetch("/api/social/instruct", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id, instruction }),
    });
    const data = await res.json();
    maStatus(data.ok ? `✉️ sent to ${agent_id}` : "⚠ " + (data.error || JSON.stringify(data)));
    if (data.ok) ma$("#ma-instruct-text").value = "";
  } catch (e) { maStatus("⚠ instruct failed: " + e.message); }
}

async function maRefreshStatus() {
  try {
    const res = await fetch("/api/swarm/status");
    const data = await res.json();
    const st = data.status;
    if (!st) return;
    const map = {};
    st.agents.forEach((a) => { map[a.agent_id] = a; });
    MA.agents.forEach((a) => {
      const s = map[a.agent_id];
      if (s) { a.status = s.status; a.last_activity = s.last_activity; }
    });
    MA.boxes.forEach((box, id) => {
      const a = map[id];
      if (!a) return;
      const stEl = box.querySelector(".ma-box-status");
      stEl.className = "ma-box-status " + a.status;
      stEl.textContent = a.status;
      const act = box.querySelector(".ma-box-activity");
      if (a.status === "idle" && a.last_activity)
        act.textContent = truncate(a.last_activity, 90);
    });
    maStageStats();
    if (MA.selectedAgent && MA.rtab === "process") maRenderProcess();
    maStatus(`swarm: ${st.running} running · ${st.done} done · ${st.error} error`);
  } catch (e) { /* backend not ready yet */ }
}

async function maShowGoals() {
  const wrap = ma$("#ma-goal-list");
  if (!wrap) return;
  try {
    const res = await fetch("/api/social/goals");
    const data = await res.json();
    const goals = data.goals || [];
    const count = ma$("#ma-goal-count");
    if (count) count.textContent = `${goals.length} goals`;
    wrap.innerHTML = goals.length
      ? goals.map((g) => `<button type="button" class="ma-goal-item" data-goal="${esc(g.goal_id)}">
          <span class="ma-goal-dot ${esc(g.status)}"></span>
          <span class="ma-goal-name">${esc(g.title)}</span>
          <span class="ma-goal-meta">${g.task_count} tasks · ${esc(g.status)}</span>
          <span class="ma-goal-open">▸ open</span>
        </button>`).join("")
      : "<div class='muted'>no goals yet</div>";
    wrap.querySelectorAll(".ma-goal-item").forEach((b) => {
      b.addEventListener("click", () => maOpenGoal(b.dataset.goal));
    });
  } catch (e) { wrap.innerHTML = "⚠ " + esc(e.message); }
}

async function maOpenGoal(goalId) {
  const detail = ma$("#ma-goal-detail");
  const head = ma$("#ma-goal-detail-head");
  const tasksEl = ma$("#ma-goal-tasks");
  if (!detail || !head || !tasksEl) return;
  try {
    const res = await fetch(`/api/social/goal?goal_id=${encodeURIComponent(goalId)}`);
    const data = await res.json();
    if (!data.ok) { maStatus("⚠ " + (data.error || "goal not found")); return; }
    const g = data.goal;
    MA.currentGoalId = goalId;
    head.innerHTML = `<strong>${esc(g.title)}</strong>
      <span class="ma-goal-id">${esc(g.goal_id)}</span>
      <span class="ma-goal-status ${esc(g.status)}">${esc(g.status)}</span>`;
    const tasks = g.tasks || [];
    tasksEl.innerHTML = tasks.length
      ? tasks.map((t) => `<div class="ma-goal-task">
          <span class="ma-goal-dot ${esc(t.status)}"></span>
          <span class="ma-goal-task-title">${esc(t.title)}</span>
          <span class="ma-goal-task-meta">${esc(t.status)}${t.assignee_agent_id ? " · " + esc(t.assignee_agent_id) : ""}</span>
        </div>`).join("")
      : '<div class="muted">no tasks yet</div>';
    detail.classList.remove("hidden");
    ma$("#ma-goal-continue").dataset.goal = goalId;
  } catch (e) { maStatus("⚠ open goal failed: " + e.message); }
}

async function maContinueGoal() {
  const btn = ma$("#ma-goal-continue");
  const goalId = btn.dataset.goal;
  MA.currentGoalId = goalId;
  // jump to Many Agents with this goal selected; the user presses Start
  await maRefreshStartGoalSelect();
  let instructions = ma$("#ma-goal-instructions").value.trim();
  if (!instructions) {
    const goalName = ma$("#ma-start-goal").selectedOptions[0]?.textContent.split(" (")[0] || "the goal";
    ma$("#ma-goal-instructions").value =
      `Continue working on the goal "${goalName}" and report progress to the team.`;
  }
  maSwitchSub("agents");
  maStatus(`goal selected: ${goalId} — press 📨 Start the goal`);
}

function maCloseGoalDetail() {
  const detail = ma$("#ma-goal-detail");
  if (detail) detail.classList.add("hidden");
}

async function maDeleteGoal() {
  const goalId = MA.currentGoalId;
  if (!goalId) return;
  if (!confirm(`Permanently delete the goal "${goalId}" and all its tasks?`)) return;
  try {
    const res = await fetch("/api/social/goal/delete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal_id: goalId }),
    });
    const data = await res.json().catch(() => null);
    if (data && data.ok) {
      maGoalStatus(`🗑 goal deleted: ${goalId}`);
      MA.currentGoalId = null;
      maCloseGoalDetail();
      maShowGoals();
      ma$("#ma-goal-name").value = "";
    } else maGoalStatus("⚠ " + ((data && data.error) || "delete failed"));
  } catch (e) { maGoalStatus("⚠ delete failed: " + e.message); }
}

// ── chat clearing (Goals tab) ────────────────────────────────────────────
function maClearStatus(msg) {
  const el = ma$("#ma-clear-status");
  if (el) el.textContent = msg;
}

async function maClearChat(scope) {
  const label = scope === "inter" ? "Inter Agent Chat" : "Global Chat Board";
  if (!confirm(`Clear the ${label}? This cannot be undone.`)) return;
  try {
    const res = await fetch("/api/social/board/clear", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope }),
    });
    const data = await res.json().catch(() => null);
    if (data && data.ok) {
      maClearStatus(`🧹 ${label} cleared (${data.cleared} messages removed)`);
      MA.boardCount = 0;      // force the chat panels to refresh
      maLoadBoard();
    } else maClearStatus("⚠ " + ((data && data.error) || "clear failed"));
  } catch (e) { maClearStatus("⚠ clear failed: " + e.message); }
}

function maBind() {
  ma$("#ma-create-goal").addEventListener("click", maCreateGoal);
  ma$("#ma-refresh-goals").addEventListener("click", maRefreshStartGoalSelect);
  ma$("#ma-send-instruction").addEventListener("click", () => maStartTeam(null));
  ma$("#ma-stop").addEventListener("click", maStopTeam);
  ma$("#ma-instruct").addEventListener("click", maInstruct);
  ma$("#ma-board-send").addEventListener("click", maPostBoard);
  ma$("#ma-pick-all").addEventListener("click", () => {
    MA.selected = new Set(MA.agents.map((a) => a.agent_id));
    maRenderPick();
  });
  ma$("#ma-pick-none").addEventListener("click", () => {
    MA.selected.clear();
    maRenderPick();
  });
  ma$("#ma-goal-continue").addEventListener("click", maContinueGoal);
  ma$("#ma-goal-delete").addEventListener("click", maDeleteGoal);
  ma$("#ma-goal-close").addEventListener("click", maCloseGoalDetail);
  ma$("#ma-clear-inter").addEventListener("click", () => maClearChat("inter"));
  ma$("#ma-clear-board").addEventListener("click", () => maClearChat("all"));
  ma$("#ma-save-settings").addEventListener("click", maSaveSettings);
  ma$("#ma-reset-settings").addEventListener("click", async () => {
    try {
      await fetch("/api/settings", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ llm_streaming: false, max_concurrent: 4,
                               social_responder: true, max_reply_rounds: 2 }),
      });
      await maLoadSettings();
      ma$("#ma-settings-status").textContent = "↺ defaults restored";
    } catch (e) { ma$("#ma-settings-status").textContent = "⚠ " + e.message; }
  });
  const boardInput = ma$("#ma-board-text");
  if (boardInput) boardInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") maPostBoard();
  });
  // sidebar sub-tabs (Agent Stage | Many Agents)
  document.querySelectorAll(".ma-subtab").forEach((btn) => {
    btn.addEventListener("click", () => maSwitchSub(btn.dataset.sub));
  });
  // right panel tabs (Agent Process | Inter Agent Chat | Global Chat Board)
  document.querySelectorAll(".ma-rtab").forEach((btn) => {
    btn.addEventListener("click", () => maSwitchRtab(btn.dataset.r));
  });
  // top-level nav: Control Center ⇄ Multi Agent
  document.querySelectorAll(".topnav-tab").forEach((btn) => {
    btn.addEventListener("click", () => maSwitchView(btn.dataset.view));
  });
  // clickable brand title → the original portal (Control Center / Graph)
  const brand = ma$("#brand-home");
  if (brand) brand.addEventListener("click", (e) => {
    e.preventDefault();
    maSwitchView("control");
    const graphTab = document.querySelector('.tab[data-tab="graph"]');
    if (graphTab) graphTab.click();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", maBoot);
} else {
  maBoot();
}
