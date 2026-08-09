/* recursiveagent.js — the Recursive Agent portal (127.0.0.8 — third portal).
 *
 * Top-level view (header nav): Control Center ⇄ Multi Agent ⇄ Recursive Agent.
 * Recursive Agent view:
 *   LEFT sidebar  — sub-tabs [⛓ Chain | 📋 Instruct | ✅ Verify]:
 *     Chain:    the agent tree (a1 → a2 → a3) with status + click to select.
 *     Instruct: send a task to an agent (Live LLM or Quick offline).
 *     Verify:   run checks on an agent (tool count, recursive capability, etc).
 *   RIGHT canvas  — sub-tabs [🧠 Agent Trace | 📊 Construction Report | 🔍 Diff View]:
 *     Agent Trace:       selected agent's process (tool calls + results).
 *     Construction Report: the full build report when an agent constructs the next.
 *     Diff View:         compare two agents.
 */
"use strict";

const ra$ = (s) => document.querySelector(s);

const RA = {
  agents: [],           // [{agent_id, name, level, tools, chain_pos}]
  selectedAgent: null,  // agent_id shown in the right trace panel
  traces: new Map(),    // agent_id → [{type, tool, content, ...}]
  reports: new Map(),   // agent_id → {steps, errors, chain, constructed}
  view: "control",      // "control" | "multiagent" | "recursive"
  sub: "chain",         // sidebar sub-tab
  rtab: "chat",         // right panel tab — default to Chat now
};

function raEsc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function raTime() {
  const d = new Date();
  return d.toTimeString().slice(0, 8);
}

// ── boot ─────────────────────────────────────────────────────────────────
async function raBoot() {
  raBindSidebar();
  raBindStage();
  await raLoadChain();
  raSwitchView(RA.view);
  // Update model badge in chat toolbar
  const modelBadge = document.getElementById("ra-chat-model-badge");
  if (modelBadge && typeof modelForPortal === "function") {
    const m = modelForPortal();
    const labels = typeof MODEL_SELECT !== "undefined" ? MODEL_SELECT.available : {};
    modelBadge.textContent = labels[m] || m;
    modelBadge.className = "badge live";
  }
  // Listen for model changes
  window.onModelChanged = function(modelId, portal) {
    if (portal === "recursive" && modelBadge) {
      const labels = typeof MODEL_SELECT !== "undefined" ? MODEL_SELECT.available : {};
      modelBadge.textContent = labels[modelId] || modelId;
      modelBadge.className = "badge live";
    }
  };
}

// ── sidebar binding ──────────────────────────────────────────────────────
function raBindSidebar() {
  ra$("#tab-recursiveagent .ra-subnav").addEventListener("click", (e) => {
    const btn = e.target.closest(".ra-subtab");
    if (!btn) return;
    raSwitchSub(btn.dataset.sub);
  });
}

function raBindStage() {
  // right panel tabs inside ra-stage
  ra$("#ra-stage .ma-rightnav").addEventListener("click", (e) => {
    const btn = e.target.closest(".ra-rtab");
    if (!btn) return;
    raSwitchRtab(btn.dataset.r);
  });

  // instruct buttons
  ra$("#ra-instruct-send").addEventListener("click", () => raInstruct(true));
  ra$("#ra-instruct-send-offline").addEventListener("click", () => raInstruct(false));

  // verify buttons
  ra$("#ra-verify-run").addEventListener("click", () => raVerifyAll());
  ra$("#ra-verify-single").addEventListener("click", () => raVerifySingle());

  // diff button
  ra$("#ra-diff-run").addEventListener("click", () => raDiff());

  // chat buttons
  ra$("#ra-chat-send").addEventListener("click", () => raChat(true));
  ra$("#ra-chat-clear").addEventListener("click", () => raChatClear());

  // Shift+Enter in chat textarea sends
  ra$("#ra-chat-message").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.shiftKey) { e.preventDefault(); raChat(true); }
  });
}

// ── chat ──────────────────────────────────────────────────────────────────
const RA_CHAT_HISTORY = [];  // {role, content, trace, toolCount, agentId}

function raChatClear() {
  RA_CHAT_HISTORY.length = 0;
  const log = ra$("#ra-chat-log");
  if (log) log.innerHTML = '<div class="ra-chat-empty">Chat cleared.</div>';
  ra$("#ra-chat-status").innerHTML = "";
}

async function raChat(live) {
  const agentId = ra$("#ra-chat-agent").value;
  const msgEl = ra$("#ra-chat-message");
  const message = msgEl.value.trim();
  const status = ra$("#ra-chat-status");
  const log = ra$("#ra-chat-log");
  if (!agentId) { status.innerHTML = '<span class="error">select an agent</span>'; return; }
  if (!message) { status.innerHTML = '<span class="error">enter a message</span>'; return; }

  // Append user message to conversation
  RA_CHAT_HISTORY.push({ role: "user", content: message, agentId });
  raRenderConversation(log);

  status.innerHTML = `<span class="running">💬 ${raEsc(agentId)} thinking…</span>`;
  msgEl.value = "";
  msgEl.style.height = "auto";

  // Append placeholder for agent response
  const agentIdx = RA_CHAT_HISTORY.length;
  RA_CHAT_HISTORY.push({ role: "agent", content: "…", agentId, live, pending: true });
  raRenderConversation(log);

  try {
    const res = await fetch("/api/recursive/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, message, live,
        model: (typeof modelForPortal === "function" ? modelForPortal() : "deepseek-v4-flash") }),
    });
    const data = await res.json();
    if (!data.ok) {
      RA_CHAT_HISTORY[agentIdx] = { role: "agent", content: `❌ ${data.error || "failed"}`, agentId, error: true };
      status.innerHTML = `<span class="error">✖ ${raEsc(data.error || "failed")}</span>`;
    } else {
      RA_CHAT_HISTORY[agentIdx] = {
        role: "agent", content: data.answer || "(empty)", agentId, live,
        trace: data.trace, toolCount: data.tool_calls || 0,
        thinkCount: (data.trace || []).filter(e => e.type === "thinking").length,
        pending: false,
      };
      status.innerHTML = `<span class="ok">✔ ${raEsc(agentId)} (${data.tool_calls || 0} tools)</span>`;
    }
  } catch (e) {
    RA_CHAT_HISTORY[agentIdx] = { role: "agent", content: `❌ ${e.message}`, agentId, error: true };
    status.innerHTML = `<span class="error">✖ ${raEsc(e.message)}</span>`;
  }
  raRenderConversation(log);
}

function raRenderConversation(log) {
  if (!log) return;
  log.querySelector(".ra-chat-empty")?.remove();

  let html = "";
  RA_CHAT_HISTORY.forEach((msg, i) => {
    if (msg.role === "user") {
      html += `<div class="ra-chat-msg ra-chat-user">
        <div class="ra-chat-role">🧑 You <span class="ra-chat-agent-tag">→ ${raEsc(msg.agentId)}</span></div>
        <div class="ra-chat-content">${raEsc(msg.content)}</div>
      </div>`;
    } else {
      const pending = msg.pending ? ' <span class="ra-chat-pending">…</span>' : '';
      const statusIcon = msg.error ? '❌' : (msg.pending ? '⏳' : '🤖');
      html += `<div class="ra-chat-msg ra-chat-agent${msg.error ? ' ra-chat-error' : ''}${msg.pending ? ' ra-chat-loading' : ''}">
        <div class="ra-chat-role">${statusIcon} ${raEsc(msg.agentId)}${pending}</div>`;

      if (!msg.pending && !msg.error && msg.trace && msg.trace.length > 0) {
        const tc = msg.toolCount || 0;
        const th = msg.thinkCount || 0;
        html += `<details class="ra-chat-trace-inline">
          <summary>▸ Agent process (${tc} tools · ${th} thinking · ${msg.trace.length} events)</summary>
          <div class="ra-chat-trace-body">${raBuildTraceHtml(msg.trace)}</div>
        </details>`;
      }

      html += `<div class="ra-chat-content md">${raMd(msg.content)}</div></div>`;
    }
  });

  log.innerHTML = html;
  log.scrollTop = log.scrollHeight;
}

function raBuildTraceHtml(trace) {
  let html = "";
  let openToolIdx = -1;
  let toolBlocks = [];
  let turnNum = 0;
  let prevType = null;

  trace.forEach((e) => {
    const t = e.type;
    if (t === "tool_call" && prevType !== "tool_call") turnNum++;
    if (t === "thinking" && prevType === null) turnNum++;

    if (t === "thinking") {
      html += `<details class="ra-step ra-think">
        <summary><span class="ra-turn-num">T${turnNum}</span> 🧠 thinking</summary>
        <pre class="ra-step-body">${raEsc((e.content || "").slice(0, 3000))}</pre></details>`;
    } else if (t === "message" || t === "text") {
      html += `<details class="ra-step ra-msg">
        <summary><span class="ra-turn-num">T${turnNum}</span> 💬 message</summary>
        <div class="ra-step-body md">${raMd(e.content || "")}</div></details>`;
    } else if (t === "tool_call") {
      const args = typeof e.args === "string" ? e.args : JSON.stringify(e.args || {}, null, 2);
      openToolIdx = toolBlocks.length;
      toolBlocks.push(`<details class="ra-step ra-tool" open>
        <summary><span class="ra-turn-num">T${turnNum}</span> 🛠 ${raEsc(e.tool || "")} <span class="ra-tool-args">${raEsc(args.slice(0, 150))}</span></summary>
        <div class="ra-step-body"></div></details>`);
    } else if (t === "tool_result") {
      const body = raEsc((e.content || "").slice(0, 2000));
      if (openToolIdx >= 0) {
        toolBlocks[openToolIdx] = toolBlocks[openToolIdx].replace(
          '<div class="ra-step-body"></div>',
          `<div class="ra-step-body"><pre class="ra-result-body">↩ ${body}</pre></div>`);
        openToolIdx = -1;
      }
    }
    prevType = t;
  });
  return html + toolBlocks.join("");
}

/** Full markdown-to-HTML: tables, code, bold, italic, lists, headings, hr, blockquote. */
function raMd(text) {
  if (!text) return "";
  let s = raEsc(text);

  // Code blocks (before other inline patterns)
  s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre class="ra-md-pre"><code>${raEsc(code.trim())}</code></pre>`);

  // Tables: | col | col |\n|---|---|\n| val | val |
  s = s.replace(/(\|[^\n]+\|\n\|[\s\-:|]+\|\n(?:\|[^\n]+\|\n?)+)/g, (m) => {
    const lines = m.trim().split("\n");
    if (lines.length < 3) return m;
    let tbl = '<table class="ra-md-table"><thead>';
    const headers = lines[0].split("|").filter(h => h.trim());
    tbl += '<tr>' + headers.map(h => `<th>${h.trim()}</th>`).join("") + '</tr></thead><tbody>';
    for (let i = 2; i < lines.length; i++) {
      const cells = lines[i].split("|").filter(c => c.trim() !== "" || i === lines.length - 1);
      if (cells.length === 0) continue;
      tbl += '<tr>' + cells.map(c => {
        const ct = c.trim();
        return `<td>${ct.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                         .replace(/`([^`]+)`/g, '<code class="ra-md-inline">$1</code>')}</td>`;
      }).join("") + '</tr>';
    }
    tbl += '</tbody></table>';
    return tbl;
  });

  // Horizontal rules
  s = s.replace(/^\s*[-*_]{3,}\s*$/gm, '<hr class="ra-md-hr">');

  // Headings
  s = s.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Blockquote
  s = s.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
  s = s.replace(/<\/blockquote>\n<blockquote>/g, '\n');

  // Bold + Italic
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Inline code
  s = s.replace(/`([^`]+)`/g, '<code class="ra-md-inline">$1</code>');

  // Bullet + numbered lists
  const parts = s.split("\n");
  let out = [];
  let inList = false;
  let listType = null;
  for (let i = 0; i < parts.length; i++) {
    const line = parts[i];
    const ulMatch = line.match(/^([ \t]*)- (.+)$/);
    const olMatch = line.match(/^([ \t]*)(\d+)\. (.+)$/);
    if (ulMatch && !inList) { out.push("<ul>"); inList = true; listType = "ul"; }
    else if (olMatch && !inList) { out.push("<ol>"); inList = true; listType = "ol"; }
    else if (inList && !ulMatch && !olMatch) {
      out.push(`</${listType}>`); inList = false; listType = null;
    }
    if (ulMatch) out.push(`<li>${ulMatch[2]}</li>`);
    else if (olMatch) out.push(`<li>${olMatch[3]}</li>`);
    else out.push(line);
  }
  if (inList) out.push(`</${listType}>`);
  s = out.join("\n");

  // Paragraphs
  s = s.replace(/\n\n+/g, '</p><p>');
  s = '<p>' + s + '</p>';
  s = s.replace(/<p><(h[1-4]|ul|ol|pre|table|blockquote|hr)/g, '<$1');
  s = s.replace(/(<\/h[1-4]>|<\/ul>|<\/ol>|<\/pre>|<\/table>|<\/blockquote>|<\/hr>)<\/p>/g, '$1');
  s = s.replace(/<p>\s*<\/p>/g, '');
  return s;
}

// ── instruct ─────────────────────────────────────────────────────────────

// ── chain loading ────────────────────────────────────────────────────────
async function raLoadChain() {
  try {
    const res = await fetch("/api/recursive/chain");
    const data = await res.json();
    RA.agents = data.agents || [];
    raRenderChain();
    raUpdateSelects();
    RA.selectedAgent = RA.agents.length > 0 ? RA.agents[0].agent_id : null;
  } catch (e) {
    ra$("#ra-chain-view").innerHTML = `<div class="muted">⚠ chain load failed: ${raEsc(e.message)}</div>`;
  }
}

function raRenderChain() {
  const wrap = ra$("#ra-chain-view");
  if (!wrap) return;
  if (!RA.agents.length) {
    wrap.innerHTML = '<div class="muted">no recursive agents found — build agent_a1 first</div>';
    return;
  }
  let html = "";
  RA.agents.forEach((a, i) => {
    html += `<div class="ra-chain-agent${a.agent_id === RA.selectedAgent ? " selected" : ""}"
        data-agent="${raEsc(a.agent_id)}" title="click to select ${raEsc(a.agent_id)}">
      <div class="ra-chain-number l${a.level || 1}">${a.level || (i + 1)}</div>
      <div class="ra-chain-info">
        <div class="ra-chain-name">${raEsc(a.agent_id)}</div>
        <div class="ra-chain-level">level ${raEsc(String(a.level))} · ${raEsc(a.status || "idle")}</div>
      </div>
      <div class="ra-chain-tools">${a.tools || "?"} tools</div>
    </div>`;
    if (i < RA.agents.length - 1) {
      html += '<div class="ra-chain-arrow">↓ generates</div>';
    }
  });
  wrap.innerHTML = html;

  // click handlers
  wrap.querySelectorAll(".ra-chain-agent").forEach((el) => {
    el.addEventListener("click", () => {
      const aid = el.dataset.agent;
      RA.selectedAgent = aid;
      raRenderChain();
      raSwitchRtab("trace");
      raRenderTrace();
      ra$("#ra-stage-stats").textContent = `${aid} selected · ${RA.agents.length} agents in chain`;
      // highlight in selects
      ra$("#ra-instruct-agent").value = aid;
      ra$("#ra-verify-agent").value = aid;
    });
  });
}

function raUpdateSelects() {
  const instruct = ra$("#ra-instruct-agent");
  const verify = ra$("#ra-verify-agent");
  const diff1 = ra$("#ra-diff-agent1");
  const diff2 = ra$("#ra-diff-agent2");
  if (!instruct || !verify) return;

  // Keep default options and add agents that exist on disk
  const known = ["agent_a1", "agent_a2", "agent_a3"];
  const existing = RA.agents.map((a) => a.agent_id);
  const all = [...new Set([...known, ...existing])];

  [instruct, verify].forEach((sel) => {
    const val = sel.value;
    // Clear options except the first placeholder
    while (sel.options.length > 1) sel.remove(1);
    // Remove placeholder if it's for verify (verify has no placeholder)
    all.forEach((id) => {
      const opt = document.createElement("option");
      opt.value = id;
      const lvl = RA.agents.find((a) => a.agent_id === id)?.level || "?";
      opt.textContent = `${id} (level ${lvl})`;
      sel.appendChild(opt);
    });
    sel.value = val || (all[all.length - 1] || "");
  });
}

// ── view switching ───────────────────────────────────────────────────────
function raSwitchView(view) {
  RA.view = view;
  // Set current portal for model selector independence
  if (typeof MODEL_SELECT !== "undefined") { MODEL_SELECT.currentPortal = view; }
  if (typeof updateBadge === "function") updateBadge();
  // hide all portal stages
  const stage = ra$("#ra-stage");
  const graphBody = ra$("#canvas-body");
  const maStage = ra$("#ma-stage");
  const canvasControls = ra$("#canvas-controls");

  if (view === "recursive") {
    if (stage) stage.classList.remove("hidden");
    if (graphBody) graphBody.classList.add("hidden");
    if (maStage) maStage.classList.add("hidden");
    if (canvasControls) canvasControls.classList.add("hidden");
  }
}

function raSwitchSub(sub) {
  RA.sub = sub;
  document.querySelectorAll("#tab-recursiveagent .ra-subtab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.sub === sub);
  });
  document.querySelectorAll("#tab-recursiveagent .ra-rpane").forEach((pane) => {
    pane.classList.toggle("active", pane.id === `ra-r-${sub}`);
  });
  if (sub === "chain") raLoadChain();
}

function raSwitchRtab(rtab) {
  RA.rtab = rtab;
  document.querySelectorAll("#ra-stage .ra-rtab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.r === rtab);
  });
  document.querySelectorAll("#ra-stage .ra-rpane").forEach((pane) => {
    pane.classList.toggle("active", pane.id === `ra-r-${rtab}`);
  });
  if (rtab === "trace") raRenderTrace();
  if (rtab === "report") raRenderReport();
}

// ── instruct ─────────────────────────────────────────────────────────────
async function raInstruct(live) {
  const agentId = ra$("#ra-instruct-agent").value;
  const task = ra$("#ra-instruct-task").value.trim();
  const status = ra$("#ra-instruct-status");
  if (!agentId) {
    status.innerHTML = '<span class="error">select an agent first</span>';
    return;
  }
  if (!task) {
    status.innerHTML = '<span class="error">enter a task</span>';
    return;
  }
  status.innerHTML = `<span class="running">▶ instructing ${raEsc(agentId)} (${live ? "Live LLM" : "offline"})…</span>`;
  RA.selectedAgent = agentId;
  raSwitchRtab("trace");
  ra$("#ra-trace-head").innerHTML = `<strong>${raEsc(agentId)}</strong> <span class="ma-process-status running">running</span>`;

  // Initialize trace
  RA.traces.set(agentId, [{ ts: raTime(), type: "start", content: `Task: ${task}` }]);
  raRenderTrace();

  const endpoint = live ? "/api/recursive/instruct" : "/api/recursive/instruct-offline";
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, task,
        model: (typeof modelForPortal === "function" ? modelForPortal() : "deepseek-v4-flash") }),
    });
    const data = await res.json();
    if (!data.ok) {
      RA.traces.get(agentId).push({ ts: raTime(), type: "error", content: data.error || "failed" });
      status.innerHTML = `<span class="error">✖ ${raEsc(data.error || "failed")}</span>`;
      ra$("#ra-trace-head").innerHTML = `<strong>${raEsc(agentId)}</strong> <span class="ma-process-status error">error</span>`;
    } else {
      // Parse trace events
      const trace = data.trace || [];
      trace.forEach((e) => {
        RA.traces.get(agentId).push({ ts: raTime(), ...e });
      });
      RA.traces.get(agentId).push({ ts: raTime(), type: "done", content: data.answer || "" });
      status.innerHTML = `<span class="ok">✔ ${raEsc(agentId)} completed (${trace.length} trace events)</span>`;
      ra$("#ra-trace-head").innerHTML = `<strong>${raEsc(agentId)}</strong> <span class="ma-process-status done">done</span>`;

      // Store report
      RA.reports.set(agentId, {
        answer: data.answer,
        chain: data.chain,
        constructed: data.constructed,
        tool_calls: data.tool_calls,
        tools_used: data.tools_used,
        elapsed: data.elapsed,
      });
    }
  } catch (e) {
    RA.traces.get(agentId).push({ ts: raTime(), type: "error", content: e.message });
    status.innerHTML = `<span class="error">✖ ${raEsc(e.message)}</span>`;
  }
  raRenderTrace();
  raLoadChain();  // refresh chain state
}

// ── trace rendering ──────────────────────────────────────────────────────
function raRenderTrace() {
  const log = ra$("#ra-trace-log");
  if (!log) return;
  if (!RA.selectedAgent) {
    log.innerHTML = '<div class="muted">select an agent and instruct it…</div>';
    return;
  }

  const entries = RA.traces.get(RA.selectedAgent) || [];
  if (!entries.length) {
    log.innerHTML = '<div class="muted">no trace yet — click ▶ Instruct</div>';
    return;
  }

  let html = "";
  let openToolIdx = -1;
  const open = [];

  entries.forEach((e) => {
    const t = e.type;
    const time = (e.ts || "").slice(0, 8);
    if (t === "start") {
      html += `<div class="ra-trace-entry"><span class="ra-trace-time">${time}</span><span class="ra-trace-text">▶ started</span></div>`;
    } else if (t === "tool_call") {
      const args = typeof e.args === "string" ? e.args : JSON.stringify(e.args || {});
      openToolIdx = open.length;
      open.push(`<details class="ra-trace-entry" open>
        <summary><span class="ra-trace-time">${time}</span><span class="ra-trace-tool">🛠 ${raEsc(e.tool || "")}</span><span style="color:var(--muted);font-size:10px">${raEsc(args.slice(0, 100))}</span></summary>
        <div class="ra-trace-result"></div></details>`);
    } else if (t === "tool_result") {
      const result = raEsc((e.content || "").slice(0, 500));
      if (openToolIdx >= 0) {
        open[openToolIdx] = open[openToolIdx].replace(
          '<div class="ra-trace-result"></div>',
          `<div class="ra-trace-result"><span class="ra-trace-time">${time}</span>↩ <span style="color:var(--muted)">${result}</span></div>`);
        openToolIdx = -1;
      }
    } else if (t === "text" || t === "message") {
      html += `<div class="ra-trace-entry"><span class="ra-trace-time">${time}</span><span class="ra-trace-text">💬 ${raEsc((e.content || "").slice(0, 200))}</span></div>`;
    } else if (t === "done") {
      html += `<div class="ra-trace-entry"><span class="ra-trace-time">${time}</span><span class="ra-trace-text ok">✔ completed</span></div>`;
    } else if (t === "error") {
      html += `<div class="ra-trace-entry"><span class="ra-trace-time">${time}</span><span class="ra-trace-text fail">✖ ${raEsc(e.content || e.error || "")}</span></div>`;
    }
  });

  html += open.join("");
  log.innerHTML = html;
  log.scrollTop = log.scrollHeight;
}

// ── report rendering ─────────────────────────────────────────────────────
function raRenderReport() {
  const body = ra$("#ra-report-body");
  if (!body) return;
  if (!RA.selectedAgent) {
    body.innerHTML = '<div class="muted">select an agent first…</div>';
    return;
  }
  const report = RA.reports.get(RA.selectedAgent);
  if (!report) {
    body.innerHTML = '<div class="muted">no report yet — instruct the agent first</div>';
    return;
  }
  body.innerHTML = `<div class="md">
    <h4>${raEsc(RA.selectedAgent)} Report</h4>
    <p><strong>Answer:</strong> ${raEsc((report.answer || "").slice(0, 1000))}</p>
    <p><strong>Elapsed:</strong> ${report.elapsed?.toFixed(1) || "?"}s</p>
    <p><strong>Tool calls:</strong> ${report.tool_calls || "0"}</p>
    <p><strong>Tools used:</strong> ${raEsc(JSON.stringify(report.tools_used || []))}</p>
    <p><strong>Chain:</strong> ${raEsc(JSON.stringify(report.chain || []))}</p>
    <p><strong>Constructed:</strong> ${raEsc(JSON.stringify(report.constructed || []))}</p>
  </div>`;
}

// ── verify ───────────────────────────────────────────────────────────────
async function raVerifyAll() {
  const agentId = ra$("#ra-verify-agent").value;
  const results = ra$("#ra-verify-results");
  const detail = ra$("#ra-verify-detail");
  if (!agentId) {
    results.innerHTML = '<span class="error">select an agent first</span>';
    return;
  }
  results.innerHTML = `<span class="running">🔍 verifying ${raEsc(agentId)}…</span>`;
  detail.innerHTML = "";

  const checks = [
    "check_tool_count",
    "check_recursive_capability",
    "evaluate_engine_comprehensiveness",
    "agent_evaluate",
    "agent_test",
  ];

  let rows = "";
  for (const check of checks) {
    try {
      const res = await fetch("/api/recursive/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, check }),
      });
      const data = await res.json();
      const ok = data.ok || data.metadata?.meets_threshold || data.metadata?.has_all || data.metadata?.is_comprehensive;
      const icon = ok ? "✅" : "❌";
      const meta = JSON.stringify(data.metadata || data).slice(0, 200);
      rows += `<div class="ra-diff-file ${ok ? "identical" : "different"}">
        <span class="ra-diff-name">${icon} ${check}</span>
        <span class="ra-diff-status">${raEsc(meta)}</span>
      </div>`;
    } catch (e) {
      rows += `<div class="ra-diff-file different">
        <span class="ra-diff-name">❌ ${check}</span>
        <span class="ra-diff-status">${raEsc(e.message)}</span>
      </div>`;
    }
  }
  results.innerHTML = `<span class="ok">✔ verification complete for ${raEsc(agentId)}</span>`;
  detail.innerHTML = rows;
}

async function raVerifySingle() {
  const agentId = ra$("#ra-verify-agent").value;
  const check = ra$("#ra-verify-check").value;
  const results = ra$("#ra-verify-results");
  if (!agentId) {
    results.innerHTML = '<span class="error">select an agent first</span>';
    return;
  }
  results.innerHTML = `<span class="running">🔍 running ${check} on ${raEsc(agentId)}…</span>`;

  try {
    const res = await fetch("/api/recursive/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, check }),
    });
    const data = await res.json();
    results.innerHTML = `<pre>${raEsc(JSON.stringify(data, null, 2))}</pre>`;
  } catch (e) {
    results.innerHTML = `<span class="error">✖ ${raEsc(e.message)}</span>`;
  }
}

// ── diff ──────────────────────────────────────────────────────────────────
async function raDiff() {
  const a1 = ra$("#ra-diff-agent1").value;
  const a2 = ra$("#ra-diff-agent2").value;
  const body = ra$("#ra-diff-body");
  if (!a1 || !a2) {
    body.innerHTML = '<div class="muted">select two agents</div>';
    return;
  }
  if (a1 === a2) {
    body.innerHTML = '<div class="muted">select two different agents</div>';
    return;
  }
  body.innerHTML = `<div class="muted">🔍 comparing ${raEsc(a1)} vs ${raEsc(a2)}…</div>`;

  try {
    const res = await fetch("/api/recursive/diff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent1: a1, agent2: a2 }),
    });
    const data = await res.json();
    let html = `<h4>${raEsc(a1)} vs ${raEsc(a2)}</h4>`;
    html += `<p><strong>Identical:</strong> ${data.identical?.length || 0} files</p>`;
    html += `<p><strong>Name-only diffs:</strong> ${data.name_only?.length || 0} files</p>`;
    html += `<p><strong>Real differences:</strong> ${data.different?.length || 0} files</p>`;

    (data.different || []).forEach((d) => {
      html += `<div class="ra-diff-file different">
        <span class="ra-diff-name">≠ ${raEsc(d.file || d)}</span>
        <span class="ra-diff-status">${raEsc(d.detail || "")}</span>
      </div>`;
    });
    (data.name_only || []).forEach((d) => {
      html += `<div class="ra-diff-file nameonly">
        <span class="ra-diff-name">≅ ${raEsc(d.file || d)}</span>
        <span class="ra-diff-status">name substitution only</span>
      </div>`;
    });
    (data.identical || []).slice(0, 10).forEach((d) => {
      html += `<div class="ra-diff-file identical">
        <span class="ra-diff-name">= ${raEsc(d.file || d)}</span>
      </div>`;
    });
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = `<div class="error">✖ ${raEsc(e.message)}</div>`;
  }
}

// ── hook into app.js topnav switching ─────────────────────────────────────
// The `app.js` handles topnav clicks with data-view attributes and shows/hides
// the matching sections. We need to hook into that flow.
function raInitTopnav() {
  // Listen for the existing topnav tab clicks and ensure RA portal is handled
  document.querySelectorAll("#topnav .topnav-tab").forEach((btn) => {
    btn.addEventListener("click", function () {
      const view = this.dataset.view;
      // Show/hide the recursive agent sidebar tab
      const raTab = ra$("#tab-recursiveagent");
      const dbTab = ra$("#tab-database");
      const runsTab = ra$("#tab-runs");

      if (view === "recursive") {
        if (raTab) raTab.classList.add("active");
        raSwitchView("recursive");
        // Hide control-center tabs that aren't relevant
        document.querySelectorAll("#tabs .tab").forEach((t) => t.parentElement && t.classList.remove("active"));
        document.querySelectorAll("#sidebar .tabpane:not(#tab-recursiveagent)").forEach((p) => p.classList.remove("active"));
      }
    });
  });

  // Also patch the brand home to support recursive view
  const brand = ra$("#brand-home");
  if (brand) {
    brand.addEventListener("click", (e) => {
      e.preventDefault();
      // Cycle to control center
      document.querySelector("#topnav .topnav-tab[data-view='control']")?.click();
    });
  }
}

// ── start ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  raInitTopnav();
  raBoot();

  // Re-check when user switches to the recursive tab
  const observer = new MutationObserver(() => {
    const tab = ra$("#tab-recursiveagent");
    if (tab && tab.classList.contains("active") && RA.view !== "recursive") {
      RA.view = "recursive";
      raSwitchView("recursive");
      raLoadChain();
    }
  });
  const tabEl = ra$("#tab-recursiveagent");
  if (tabEl) {
    observer.observe(tabEl, { attributes: true, attributeFilter: ["class"] });
  }
});
