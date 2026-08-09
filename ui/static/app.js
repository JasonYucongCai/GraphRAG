/* Graph Knowledge Network — Control Center (frontend logic) */
"use strict";

const $ = (sel) => document.querySelector(sel);
const CAT_COLORS = {
  subject: "#4caf7d", paper: "#4c9aff", concept: "#ffab4c",
  benchmark: "#b57ff2", experience: "#ef5350", note: "#4cc2ff",
};
// per-project category colors (categories.json) — loaded from the server;
// falls back to CAT_COLORS / #888 when no project is open or the map lacks
// a category (classification projects have their own sets: root/menlei/
// dalei/zhonglei/xiaolei, section/division/group/class, …)
let DB_COLORS = { default: "#8aa0b0", map: {} };
function catColor(category) {
  return (DB_COLORS.map && DB_COLORS.map[category]) || CAT_COLORS[category]
    || DB_COLORS.default || "#8aa0b0";
}
async function loadDbColors() {
  try {
    const proj = $("#db-project-select")?.value || "";
    const r = await api(`/api/database/categories?project=${encodeURIComponent(proj)}`);
    if (r && r.map) DB_COLORS = { default: r.default || "#8aa0b0", map: r.map };
  } catch (e) { /* keep fallback */ }
  if (state.viz === "interactive") loadInteractive();
  else if (state.viz === "mermaid") loadMermaid();
}
const CAT_LABELS = {
  subject: "subject", paper: "paper", concept: "concept",
  benchmark: "benchmark", experience: "experience", note: "note",
};

// ── state ──────────────────────────────────────────────────────────────────
const state = {
  nodes: [],              // full node list (sidebar)
  viewNodes: [],          // current view nodes {node_id, entryname, category, x, y}
  viewEdges: [],          // current view edges
  viewAnchor: null,       // anchor node_id (highlight), if any
  view: "global",         // global | local
  depth: 3,
  selected: null,
  // canvas geometry + interaction
  w: 900, h: 640,
  transform: { k: 1, x: 0, y: 0 },
  drag: null,             // {mode:'node'|'pan', startX, startY, origX, origY, moved}
};

// ── api helper ─────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${path}`);
  return data;
}

// ── tabs ───────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tabpane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
  });
});

// ── boot ───────────────────────────────────────────────────────────────────
const MODEL_SELECT = {
  available: {},           // {model_id: label}
  active: "deepseek-v4-flash",
  perPortal: { control: null, multiagent: null, recursive: null },
  currentPortal: "control",
};

function modelForPortal() {
  const override = MODEL_SELECT.perPortal[MODEL_SELECT.currentPortal];
  return override || MODEL_SELECT.active;
}

function renderModelSelector() {
  const list = document.getElementById("model-dropdown-list");
  if (!list) return;
  const current = modelForPortal();
  let html = "";
  Object.entries(MODEL_SELECT.available).forEach(([id, label]) => {
    const active = id === current ? " active" : "";
    const dotClass = id.includes("pro") ? "pro" : "flash";
    html += `<button class="model-dropdown-item${active}" data-model="${esc(id)}">
      <span class="model-dot ${dotClass}"></span> ${esc(label)} <span style="color:var(--muted);font-size:10px;margin-left:auto">${esc(id)}</span>
    </button>`;
  });
  html += '<hr class="model-dropdown-divider">';
  html += `<div style="font-size:10px;color:var(--muted);padding:4px 12px">Portal: ${esc(MODEL_SELECT.currentPortal)}</div>`;
  list.innerHTML = html;
  list.querySelectorAll(".model-dropdown-item").forEach(btn => {
    btn.addEventListener("click", () => {
      MODEL_SELECT.perPortal[MODEL_SELECT.currentPortal] = btn.dataset.model;
      updateBadge();
      document.getElementById("model-selector").classList.add("hidden");
      if (window.onModelChanged) window.onModelChanged(btn.dataset.model, MODEL_SELECT.currentPortal);
    });
  });
}

function updateBadge() {
  const badge = document.getElementById("provider-badge");
  if (!badge) return;
  const model = modelForPortal();
  const label = MODEL_SELECT.available[model] || model;
  badge.textContent = label;
  badge.className = "badge " + (model.includes("pro") ? "live pro" : "live");
}

function esc(s) { return String(s || "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }

async function boot() {
  try {
    const h = await api("/api/health");
    MODEL_SELECT.available = h.available_models || {"deepseek-v4-flash": "DeepSeek V4 Flash"};
    MODEL_SELECT.active = h.model || "deepseek-v4-flash";
    updateBadge();
    renderModelSelector();
    $("#health-line").textContent = `${h.workspace} · ${h.tools.length} tools · ${h.model}`;

    const badge = document.getElementById("provider-badge");
    badge.addEventListener("click", (e) => {
      e.stopPropagation();
      const dd = document.getElementById("model-selector");
      dd.classList.toggle("hidden");
      renderModelSelector();
    });
    document.addEventListener("click", () => {
      const dd = document.getElementById("model-selector");
      if (dd) dd.classList.add("hidden");
    });
  } catch (e) {
    $("#health-line").textContent = "server unreachable: " + e.message;
  }
  await refreshSummary();
  await refreshNodes();
  await loadGraph();
  await refreshRuns();
  await loadDbProjects();
  await loadDbNotes();
  await loadDbColors();
}

// ── graph summary cards ────────────────────────────────────────────────────
async function refreshSummary() {
  try {
    const s = await api("/api/graph/summary");
    const cards = $("#summary-cards");
    cards.innerHTML = "";
    [
      ["nodes", s.nodes], ["edges", s.edges], ["density", s.density],
      ["violations", s.violations], ["components", s.components],
    ].forEach(([l, v]) => {
      const c = document.createElement("div");
      c.className = "card";
      c.innerHTML = `<div class="v">${v}</div><div class="l">${l}</div>`;
      cards.appendChild(c);
    });
  } catch (e) { console.warn(e); }
}

// ── node list ──────────────────────────────────────────────────────────────
async function refreshNodes() {
  const data = await api("/api/graph/nodes");
  state.nodes = data.nodes;
  $("#node-datalist").innerHTML = data.nodes.map((n) =>
    `<option value="${n.node_id}">${escapeHtml(n.entryname)}</option>`).join("");
  renderNodeList(data.nodes);
}

function renderNodeList(nodes) {
  const list = $("#node-list");
  list.innerHTML = "";
  nodes.forEach((n) => {
    const el = document.createElement("div");
    el.className = "list-item";
    el.innerHTML = `
      <div class="name">${escapeHtml(n.entryname)}
        <span class="cat" style="background:${catColor(n.category)}22;color:${catColor(n.category)}">
          ${CAT_LABELS[n.category] || n.category}</span>
      </div>
      <div class="meta">${escapeHtml(String(n.node_id))} · in ${n.in_degree} · out ${n.out_degree} · pr ${n.pagerank}</div>`;
    el.addEventListener("click", () => selectNode(n.node_id));
    list.appendChild(el);
  });
}

$("#node-filter").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  renderNodeList(state.nodes.filter((n) =>
    String(n.node_id).toLowerCase().includes(q) || n.entryname.toLowerCase().includes(q)));
});

// ── node selection → drawer ────────────────────────────────────────────────
function openDrawer() { $("#drawer").classList.remove("hidden"); }
function closeDrawer() { $("#drawer").classList.add("hidden"); }

async function selectNode(nodeId) {
  state.selected = nodeId;
  openDrawer();
  try {
    const n = await api(`/api/graph/node/${encodeURIComponent(nodeId)}`);
    $("#drawer-title").textContent = n.entryname;
    const cColor = catColor(n.category);
    let html = `
      <div class="kv"><span class="k">id</span><span class="v">${escapeHtml(String(n.node_id))}</span></div>
      <div class="kv"><span class="k">category</span><span class="v" style="color:${cColor}">${n.category}</span></div>
      <div class="kv"><span class="k">version</span><span class="v">${n.version}</span></div>
      <div class="kv"><span class="k">in/out</span><span class="v">${n.stats.in_degree} / ${n.stats.out_degree}</span></div>
      <div class="kv"><span class="k">pagerank</span><span class="v">${n.stats.pagerank}</span></div>
      <p class="desc">${escapeHtml(n.description)}</p>
      <h3>⬅ incoming</h3>`;
    n.incoming.forEach((i) => {
      html += `<div class="neighbor"><span>${escapeHtml(i.entryname)}</span>
        <span style="color:${cColor}">${i.relation}</span></div>`;
    });
    html += `<h3>➡ outgoing</h3>`;
    n.outgoing.forEach((o) => {
      html += `<div class="neighbor"><span>${escapeHtml(o.entryname)}</span>
        <span style="color:${catColor}">${o.relation}</span></div>`;
    });
    $("#drawer-body").innerHTML = html;
  } catch (e) { console.warn(e); }
  // in local-view mode, re-materialize the selected node's local graph
  if (state.view === "local") loadGraph();
}

$("#drawer-close").addEventListener("click", closeDrawer);
$("#btn-drawer").addEventListener("click", () => {
  if ($("#drawer").classList.contains("hidden")) {
    if (state.selected) selectNode(state.selected);
    else openDrawer();
  } else {
    closeDrawer();
  }
});

// interactive iframe → SPA: a node click opens the detail drawer
// (instead of a popup). Works for both the global and local views.
window.addEventListener("message", (ev) => {
  const d = ev.data || {};
  if (d.type === "graph-node-click" && d.nodeId) {
    selectNode(d.nodeId);
  }
});

// ── graph: layout (Fruchterman-Reingold with bounded displacement) ─────────
const LAYOUT_PAD = 70;   // room for labels around the edges

function layoutNodes() {
  const W = state.w, H = state.h;
  const nodes = state.viewNodes, n = nodes.length, edges = state.viewEdges;
  if (!n) return;

  // initial placement: circle + jitter (breaks exact overlaps deterministically)
  const R = Math.min(W, H) * 0.38;
  nodes.forEach((nd, i) => {
    const a = (i / n) * Math.PI * 2;
    nd.x = W / 2 + R * Math.cos(a) + (Math.random() - 0.5) * 16;
    nd.y = H / 2 + R * Math.sin(a) + (Math.random() - 0.5) * 16;
  });

  const area = Math.max(1, (W - 2 * LAYOUT_PAD)) * Math.max(1, (H - 2 * LAYOUT_PAD));
  const k = 0.75 * Math.sqrt(area / n);          // ideal edge length
  const iters = n > 120 ? 160 : 320;
  const idx = new Map(nodes.map((nd, i) => [String(nd.node_id), i]));

  for (let it = 0; it < iters; it++) {
    const temp = Math.max(0.2, (1 - it / iters)) * k * 0.12;   // max displacement/iter
    const disp = nodes.map(() => ({ x: 0, y: 0 }));

    // repulsion (O(n²)) — with jitter so exact overlaps separate
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = nodes[i].x - nodes[j].x;
        let dy = nodes[i].y - nodes[j].y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 4) {
          dx = (Math.random() - 0.5) * 3;
          dy = (Math.random() - 0.5) * 3;
          d2 = dx * dx + dy * dy || 1;
        }
        const d = Math.sqrt(d2);
        const f = (k * k) / d;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        disp[i].x += fx; disp[i].y += fy;
        disp[j].x -= fx; disp[j].y -= fy;
      }
    }

    // attraction along edges
    for (const e of edges) {
      const ai = idx.get(String(e.source));
      const bi = idx.get(String(e.target));
      if (ai === undefined || bi === undefined) continue;
      let dx = nodes[ai].x - nodes[bi].x;
      let dy = nodes[ai].y - nodes[bi].y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (d * d) / k;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      disp[ai].x -= fx; disp[ai].y -= fy;
      disp[bi].x += fx; disp[bi].y += fy;
    }

    // apply (temperature-capped) + gentle gravity + soft bounds
    for (let i = 0; i < n; i++) {
      const norm = Math.hypot(disp[i].x, disp[i].y);
      if (norm > 0) {
        const lim = Math.min(norm, temp);
        nodes[i].x += (disp[i].x / norm) * lim;
        nodes[i].y += (disp[i].y / norm) * lim;
      }
      nodes[i].x += (W / 2 - nodes[i].x) * 0.004;
      nodes[i].y += (H / 2 - nodes[i].y) * 0.004;
      nodes[i].x = Math.max(LAYOUT_PAD, Math.min(W - LAYOUT_PAD, nodes[i].x));
      nodes[i].y = Math.max(LAYOUT_PAD, Math.min(H - LAYOUT_PAD, nodes[i].y));
    }
  }
}

// ── graph: render (two layers — scaled world + constant-size labels) ───────
function renderGraph() {
  const svg = $("#graph-canvas");
  const { k, x, y } = state.transform;

  let markers = `<defs>
    <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
      <polygon points="0 0, 8 3, 0 6" fill="#4a5c6c"/>
    </marker>
  </defs>`;

  // ── world layer (scaled): edges + node circles ──
  let edgesHtml = "";
  state.viewEdges.forEach((e) => {
    const a = state.viewNodes.find((n) => String(n.node_id) === String(e.source));
    const b = state.viewNodes.find((n) => String(n.node_id) === String(e.target));
    if (!a || !b) return;
    edgesHtml += `<line class="edge" x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}"/>`;
  });

  let circlesHtml = "";
  state.viewNodes.forEach((n) => {
    const color = catColor(n.category);
    const r = String(n.node_id) === String(state.viewAnchor) ? 14 : 9;
    circlesHtml += `<g class="node" data-id="${escapeHtml(String(n.node_id))}">
      <circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${r}" fill="${color}" fill-opacity=".85"/>
    </g>`;
  });

  // ── label layer (unscaled): constant-size labels at screen coords ──
  let labelsHtml = "";
  const showLabels = k >= 0.55;   // hide text when zoomed way out (declutter)
  state.viewNodes.forEach((n) => {
    const isAnchor = String(n.node_id) === String(state.viewAnchor);
    if (!showLabels && !isAnchor) return;
    const r = isAnchor ? 14 : 9;
    const sx = n.x * k + x;
    const sy = n.y * k + y - r * k - 4;         // above the (scaled) circle
    const label = truncate(n.entryname, 26);
    labelsHtml += `<g class="nlabel" data-id="${escapeHtml(String(n.node_id))}">
      <text class="shadow" x="${sx.toFixed(1)}" y="${sy.toFixed(1)}">${escapeHtml(label)}</text>
      <text x="${(sx + 1).toFixed(1)}" y="${(sy + 1).toFixed(1)}">${escapeHtml(label)}</text>
    </g>`;
  });

  // edge labels only when the graph is small enough to stay readable
  if (state.viewEdges.length <= 20) {
    state.viewEdges.forEach((e) => {
      const a = state.viewNodes.find((n) => String(n.node_id) === String(e.source));
      const b = state.viewNodes.find((n) => String(n.node_id) === String(e.target));
      if (!a || !b) return;
      const sx = ((a.x + b.x) / 2) * k + x;
      const sy = ((a.y + b.y) / 2) * k + y - 6;
      labelsHtml += `<text class="edge-label" x="${sx.toFixed(1)}" y="${sy.toFixed(1)}">${escapeHtml(e.relation)}</text>`;
    });
  }

  svg.innerHTML = markers +
    `<g id="world" transform="translate(${x.toFixed(2)},${y.toFixed(2)}) scale(${k.toFixed(4)})">${edgesHtml}${circlesHtml}</g>` +
    `<g id="labels">${labelsHtml}</g>`;
}

function truncate(s, max) {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

// fast update of one node's circle + label during drag (no full rebuild)
function updateNodeVisual(id) {
  const n = state.viewNodes.find((v) => String(v.node_id) === String(id));
  if (!n) return;
  const svg = $("#graph-canvas");
  const { k, x, y } = state.transform;
  const sel = `[data-id="${CSS.escape(String(id))}"]`;
  const circle = svg.querySelector(`.node${sel} circle`);
  if (circle) {
    circle.setAttribute("cx", n.x);
    circle.setAttribute("cy", n.y);
  }
  const label = svg.querySelector(`.nlabel${sel}`);
  if (label) {
    const r = String(n.node_id) === String(state.viewAnchor) ? 14 : 9;
    label.setAttribute("x", n.x * k + x);
    label.setAttribute("y", n.y * k + y - r * k - 4);
    // second <text> (non-shadow) follows the group x/y
    const t2 = label.querySelector("text:not(.shadow)");
    if (t2) t2.setAttribute("x", n.x * k + x + 1);
  }
}

// ── graph: interaction (drag nodes, pan, zoom) ─────────────────────────────
function svgPoint(e) {
  const rect = $("#graph-canvas").getBoundingClientRect();
  return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

function onMouseDown(e) {
  const svg = $("#graph-canvas");
  if (e.button !== 0) return;
  const nodeEl = e.target.closest ? e.target.closest(".node") : null;
  const p = svgPoint(e);
  if (nodeEl) {
    const id = nodeEl.dataset.id;
    const n = state.viewNodes.find((v) => String(v.node_id) === id);
    if (!n) return;
    state.drag = { mode: "node", id, startX: p.x, startY: p.y, origX: n.x, origY: n.y, moved: false };
    svg.classList.add("panning");
    e.preventDefault();
  } else {
    state.drag = { mode: "pan", startX: p.x, startY: p.y, origX: state.transform.x, origY: state.transform.y, moved: false };
    svg.classList.add("panning");
  }
}

function onMouseMove(e) {
  if (!state.drag) return;
  const p = svgPoint(e);
  const d = state.drag;
  const dx = p.x - d.startX, dy = p.y - d.startY;
  if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
  if (d.mode === "node") {
    const n = state.viewNodes.find((v) => String(v.node_id) === d.id);
    if (!n) return;
    n.x = d.origX + dx / state.transform.k;
    n.y = d.origY + dy / state.transform.k;
    updateNodeVisual(d.id);
  } else {
    state.transform.x = d.origX + dx;
    state.transform.y = d.origY + dy;
    renderGraph();
  }
}

function onMouseUp() {
  state.drag = null;
  $("#graph-canvas").classList.remove("panning");
}

function onClickSvg(e) {
  // labels live in a separate layer; find the owning node via data-id
  const nodeEl = e.target.closest ? e.target.closest(".node, .nlabel") : null;
  if (nodeEl) selectNode(nodeEl.dataset.id);
}

function onWheel(e) {
  e.preventDefault();
  const p = svgPoint(e);
  const { k } = state.transform;
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const nk = Math.min(4, Math.max(0.2, k * factor));
  // zoom around cursor
  state.transform.x = p.x - ((p.x - state.transform.x) / k) * nk;
  state.transform.y = p.y - ((p.y - state.transform.y) / k) * nk;
  state.transform.k = nk;
  renderGraph();
}

function setupCanvasInteractions() {
  const svg = $("#graph-canvas");
  svg.addEventListener("mousedown", onMouseDown);
  svg.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp);
  svg.addEventListener("click", onClickSvg);
  svg.addEventListener("wheel", onWheel, { passive: false });
  // double-click: zoom into a node, or reset view
  svg.addEventListener("dblclick", (e) => {
    const target = e.target.closest ? e.target.closest(".node, .nlabel") : null;
    if (target) {
      const n = state.viewNodes.find((v) => String(v.node_id) === target.dataset.id);
      if (n) {
        const p = svgPoint(e);
        state.transform.k = Math.max(state.transform.k, 1.6);
        const { k } = state.transform;
        state.transform.x = p.x - n.x * k;
        state.transform.y = p.y - n.y * k;
        renderGraph();
      }
    } else {
      state.transform = { k: 1, x: 0, y: 0 };
      renderGraph();
    }
  });
  // track canvas size — re-render preserving positions
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => {
      const rect = svg.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        state.w = rect.width; state.h = rect.height;
        if (state.viewNodes.length) renderGraph();
      }
    });
    ro.observe(svg);
  } else {
    window.addEventListener("resize", () => {
      const rect = svg.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        state.w = rect.width; state.h = rect.height;
        if (state.viewNodes.length) renderGraph();
      }
    });
  }
}

// ── view loading: global vs local ──────────────────────────────────────────
function setViewData(nodes, edges, anchor, info) {
  state.viewNodes = nodes.map((n) => ({ ...n }));
  state.viewEdges = edges;
  state.viewAnchor = anchor;
  $("#canvas-info").textContent = info;
  layoutNodes();
  renderGraph();
}

async function loadGraph() {
  try {
    if (state.view === "global") {
      const [nodes, edges, summary] = await Promise.all([
        api("/api/graph/nodes"),
        api("/api/graph/edges"),
        api("/api/graph/summary"),
      ]);
      setViewData(nodes.nodes, edges.edges, null,
        `global view: ${nodes.nodes.length} nodes · ${edges.edges.length} edges · ${summary.components} component${summary.components !== 1 ? "s" : ""}`);
    } else if (state.selected) {
      const local = await api(`/api/graph/local/${encodeURIComponent(state.selected)}?depth=${state.depth}`);
      setViewData(local.nodes, local.edges, local.anchor,
        `L${local.depth}(${local.anchor}): ${local.stats.n} nodes · ${local.stats.m} edges · diameter ${local.stats.diameter}`);
    } else {
      $("#canvas-info").textContent = "select a node to view its local graph";
    }
  } catch (e) { console.warn(e); }
}

$("#view-global").addEventListener("click", () => {
  state.view = "global";
  $("#view-global").classList.add("active"); $("#view-local").classList.remove("active");
  loadGraph();
});
$("#view-local").addEventListener("click", () => {
  state.view = "local";
  $("#view-local").classList.add("active"); $("#view-global").classList.remove("active");
  if (state.selected) loadGraph();
});
$("#depth-select").addEventListener("change", (e) => {
  state.depth = Number(e.target.value);
  if (state.view === "local") loadGraph();
});

// ── vector search ───────────────────────────────────────────────────────────
$("#btn-search").addEventListener("click", async () => {
  const query = $("#search-query").value.trim();
  const k = Number($("#search-k").value || 10);
  const out = $("#search-results");
  if (!query) return;
  out.innerHTML = `<div class="status running">searching…</div>`;
  try {
    const r = await api("/api/search", { method: "POST", body: { query, k } });
    let html = "";
    if (r.nodes.length) {
      html += `<h3>nodes</h3>`;
      r.nodes.forEach((n) => {
        html += `<div class="list-item" onclick="selectNode('${escapeHtml(String(n.node_id))}')">
          <div class="name">${escapeHtml(n.entryname)}</div>
          <div class="meta">score ${n.score}</div></div>`;
      });
    }
    if (r.chunks.length) {
      html += `<h3>chunks</h3>`;
      r.chunks.forEach((c) => {
        html += `<div class="result-chunk"><div class="head">${escapeHtml(c.chunk_id)} · sim ${c.sim}</div>
          <div class="txt">${escapeHtml(c.text)}</div></div>`;
      });
    }
    out.innerHTML = html || `<div class="status">no results</div>`;
  } catch (e) {
    out.innerHTML = `<div class="status error">${escapeHtml(e.message)}</div>`;
  }
});

// ── agent console (unified codex agents, foldable process) ──────────────────
function setStatus(cls, msg) {
  const el = $("#agent-status");
  el.className = "status " + cls;
  el.textContent = msg;
}

// ── markdown rendering (marked.js; content HTML-escaped first for safety) ──
function renderMarkdown(text) {
  const safe = escapeHtml(text || "");
  if (window.marked) {
    return `<div class="md">${marked.parse(safe, { breaks: true, gfm: true })}</div>`;
  }
  return `<div class="md"><pre>${safe}</pre></div>`;
}

// ── streaming agent chat (SSE) ──────────────────────────────────────────────
// renders events progressively: thinking → messages → tool calls → answer,
// exactly as the agent produces them (no "stuck then dump").
let streamState = null;   // {trace: [], answer: '', textEl, box, status}

function newStep(kind, step) {
  const details = document.createElement("details");
  details.className = "pt-step";
  details.dataset.kind = kind;
  details.open = kind === "tool";
  const s = document.createElement("summary");
  const b = document.createElement("div");
  b.className = "pt-body";
  details.appendChild(s);
  details.appendChild(b);
  return { details, s, b };
}

function stepLabel(kind, step) {
  const n = (step.content || "").length;
  if (kind === "thinking") return `🧠 thinking (${n} chars)`;
  if (kind === "message") return `💬 message (${n} chars)`;
  if (kind === "tool") {
    const args = step.args ? JSON.stringify(step.args) : "";
    return `🛠 ${step.tool}(${args})`;
  }
  if (kind === "toolresult") return `↩ result of ${step.tool}`;
  return step.type;
}

function stepBody(kind, step) {
  if (kind === "message") return renderMarkdown(step.content || "");
  if (kind === "thinking" || kind === "toolresult") {
    return `<pre class="mono">${escapeHtml(step.content || "")}</pre>`;
  }
  if (kind === "tool") {
    return `<span class="pt-toolargs">args: ${escapeHtml(JSON.stringify(step.args || {}))}</span>`;
  }
  return `<pre class="mono">${escapeHtml(step.content || JSON.stringify(step))}</pre>`;
}

function initStreamUI() {
  const box = $("#process-trace");
  box.innerHTML = "";
  const ans = $("#agent-answer");
  ans.innerHTML = "";
  $("#process-details").classList.remove("hidden");
  $("#agent-answer").classList.remove("hidden");
  $("#process-summary").textContent = "▸ Agentic process (running…)";
  streamState = {
    trace: [], answer: "", box, ans,
    steps: {},       // index → {details, s, b}
    counters: { tool_call: 0, thinking: 0, message: 0, tool_result: 0 },
  };
}

function handleStreamEvent(ev) {
  if (!streamState) return;
  const t = ev.type;
  const st = streamState;
  const idx = st.trace.length;
  st.trace.push(ev);

  // progressive assistant-text deltas: accumulate into a live message step
  if (t === "message_delta") {
    if (!st.activeMsg) {
      const { details, s, b } = newStep("message", ev);
      s.textContent = "💬 message (streaming…)";
      st.box.appendChild(details);
      st.activeMsg = { details, s, b, text: "" };
      st.steps[idx] = st.activeMsg;
    }
    st.activeMsg.text += ev.content || "";
    st.activeMsg.s.textContent = `💬 message (${st.activeMsg.text.length} chars)`;
    st.activeMsg.b.innerHTML = renderMarkdown(st.activeMsg.text);
    return;
  }
  if (t === "message") {
    // finalize any streaming message step, else create a new one
    if (st.activeMsg) {
      st.activeMsg.text = ev.content || st.activeMsg.text;
      st.activeMsg.s.textContent = `💬 message (${st.activeMsg.text.length} chars)`;
      st.activeMsg.b.innerHTML = renderMarkdown(st.activeMsg.text);
      st.activeMsg = null;
    } else {
      const { details, s, b } = newStep("message", ev);
      s.textContent = stepLabel("message", ev);
      b.innerHTML = stepBody("message", ev);
      st.box.appendChild(details);
      st.steps[idx] = { details, s, b };
    }
    st.counters.message = (st.counters.message || 0) + 1;
    updateProcessSummary();
    return;
  }

  if (t === "thinking" || t === "tool_call" || t === "tool_result") {
    const kind = t === "tool_call" ? "tool"
      : t === "tool_result" ? "toolresult"
      : t;
    const { details, s, b } = newStep(kind, ev);
    s.textContent = stepLabel(kind, ev);
    b.innerHTML = stepBody(kind, ev);
    st.box.appendChild(details);
    st.steps[idx] = { details, s, b };
    st.counters[t] = (st.counters[t] || 0) + 1;
    updateProcessSummary();
    // keep latest tool open
    if (kind === "tool") {
      Object.values(st.steps).forEach((x) => { x.details.open = false; });
      details.open = true;
    }
  } else if (t === "text" || t === "answer") {
    // final answer: render progressively (streamed markdown chunk)
    st.answer += ev.content || "";
    st.ans.innerHTML = renderMarkdown(st.answer);
  } else if (t === "error") {
    setStatus("error", ev.error || "agent error");
  }
}

function updateProcessSummary() {
  if (!streamState) return;
  const c = streamState.counters;
  $("#process-summary").textContent =
    `▸ Agentic process (${c.tool_call || 0} tools · ${c.thinking || 0} thinking · ${c.message || 0} messages)`;
}

async function streamAgentChat(agent, node, task) {
  initStreamUI();
  setStatus("running", `${agent} running${node ? " on " + node : ""}…`);
  const resp = await fetch("/api/agent/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent, node, task }),
  });
  if (!resp.ok || !resp.body) throw new Error(`stream failed: ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let tokens = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE: data lines separated by blank lines
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const raw = line.slice(5).trim();
      if (!raw) continue;
      let ev;
      try { ev = JSON.parse(raw); } catch { continue; }
      if (ev.type === "end") { tokens = ev.tokens || 0; continue; }
      handleStreamEvent(ev);
    }
  }
  setStatus("done", `✓ ${agent} · ${streamState.answer.length} chars · ${tokens} tokens`);
}

$("#btn-codex-agent").addEventListener("click", async () => {
  const agent = $("#codex-agent-select").value;
  const node = $("#codex-agent-node").value.trim();
  const task = $("#codex-agent-task").value.trim();
  if (!task) { setStatus("error", "task/message required"); return; }
  try {
    await streamAgentChat(agent, node, task);
    refreshSummary(); refreshNodes(); refreshRuns();
  } catch (e) {
    setStatus("error", e.message);
  }
});

// ── runs log ────────────────────────────────────────────────────────────────
async function refreshRuns() {
  try {
    const r = await api("/api/runs");
    const list = $("#run-list");
    list.innerHTML = "";
    if (!r.runs.length) { list.innerHTML = `<div class="status">no runs yet</div>`; return; }
    r.runs.slice().reverse().forEach((run) => {
      const el = document.createElement("div");
      el.className = "run-item";
      el.innerHTML = `<div class="ts">${escapeHtml(run.ts || "")} · ${run.agent || "agent"}</div>
        <pre>${escapeHtml(JSON.stringify(run, null, 1).slice(0, 700))}</pre>`;
      list.appendChild(el);
    });
  } catch (e) { console.warn(e); }
}

// ── visualization mode: SVG | Interactive | Mermaid ─────────────────────────
state.viz = "svg";

function setViz(mode) {
  state.viz = mode;
  $("#viz-svg").classList.toggle("active", mode === "svg");
  $("#viz-interactive").classList.toggle("active", mode === "interactive");
  $("#viz-mermaid").classList.toggle("active", mode === "mermaid");
  $("#graph-canvas").classList.toggle("hidden", mode !== "svg");
  $("#viz-frame").classList.toggle("hidden", mode !== "interactive");
  $("#mermaid-view").classList.toggle("hidden", mode !== "mermaid");
  if (mode === "svg") {
    if (state.viewNodes.length) renderGraph();
  } else if (mode === "interactive") {
    loadInteractive();
  } else if (mode === "mermaid") {
    loadMermaid();
  }
}

function vizParams() {
  const anchor = state.view === "local" && state.selected ? state.selected : null;
  return `?depth=${state.depth}${anchor ? `&node=${encodeURIComponent(anchor)}` : ""}`;
}

async function loadInteractive() {
  const iframe = $("#viz-frame");
  iframe.src = "/api/visual/interactive" + vizParams();
}

async function loadMermaid() {
  try {
    const r = await api("/api/visual/mermaid" + vizParams());
    $("#mermaid-view").textContent = r.mermaid;
  } catch (e) {
    $("#mermaid-view").textContent = "mermaid fetch failed: " + e.message;
  }
}

$("#viz-svg").addEventListener("click", () => setViz("svg"));
$("#viz-interactive").addEventListener("click", () => setViz("interactive"));
$("#viz-mermaid").addEventListener("click", () => setViz("mermaid"));

// when switching global/local/depth, refresh the active viz
const _origLoadGraph = loadGraph;
loadGraph = async function () {
  await _origLoadGraph();
  if (state.viz === "interactive") loadInteractive();
  else if (state.viz === "mermaid") loadMermaid();
};

// ── database tab (note project store) ────────────────────────────────────────
function dbStatus(cls, msg) {
  const el = $("#db-status");
  el.className = "status " + cls;
  el.textContent = msg;
}

async function loadDbProjects() {
  try {
    const r = await api("/api/database/projects");
    const sel = $("#db-project-select");
    sel.innerHTML = `<option value="">— none open —</option>` +
      r.projects.map((p) =>
        `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)} (${p.nodes} notes)</option>`).join("");
    if (r.current) {
      sel.value = r.current;
      dbStatus("done", `project open: ${r.current}`);
    }
  } catch (e) { dbStatus("error", e.message); }
  loadDbSupplements();
}

// the OpenSupplement dropdown ALWAYS shows the SELECTED project's bundles —
// never a stale server-side "current" (project-scoped via ?project=).
async function loadDbSupplements() {
  try {
    const proj = $("#db-project-select")?.value || "";
    const r = await api(`/api/database/supplements?project=${encodeURIComponent(proj)}`);
    const sel = $("#db-supplement-select");
    const prev = sel.value;                       // preserve current selection
    const sups = r.supplements || [];
    sel.innerHTML = `<option value="">— no supplements —</option>` +
      sups.map((s) =>
        `<option value="${escapeHtml(s.slug)}">${escapeHtml(s.name)} ` +
        `(${s.nodes} notes${s.active ? " · active" : ""})</option>`).join("");
    // keep the previous choice when it still exists; otherwise prefer an
    // ACTIVE supplement so "✕ close" works right after OpenSupplement / reload
    const opts = Array.from(sel.options).map((o) => o.value);
    if (prev && opts.includes(prev)) {
      sel.value = prev;
    } else {
      const act = sups.find((s) => s.active);
      sel.value = act ? act.slug : "";
    }
  } catch (e) { /* non-fatal */ }
}

// switching the selected project immediately re-scopes the supplement list
// and the category colors (selected project, not server-side "current")
$("#db-project-select").addEventListener("change", () => { loadDbSupplements(); loadDbColors(); });

async function loadDbNotes() {
  try {
    const r = await api("/api/database/notes");
    const list = $("#db-note-list");
    if (!r.project) {
      list.innerHTML = `<div class="status">open or create a project first</div>`;
      return;
    }
    if (!r.notes.length) {
      list.innerHTML = `<div class="status">no notes — click "export graph → notes"</div>`;
      return;
    }
    list.innerHTML = "";
    r.notes.forEach((n) => {
      const el = document.createElement("div");
      el.className = "list-item note-item";
      el.innerHTML = `<div class="name">${escapeHtml(n.entryname)}
          <span class="tag">${escapeHtml(n.category)}</span><span class="tag">${n.vcl_count} vcl</span></div>
        <div class="meta">${escapeHtml(String(n.node_id))} · ${n.link_count} links · ${n.version}</div>`;
      el.addEventListener("click", () => openNoteEditor(n.node_id, n.entryname));
      list.appendChild(el);
    });
  } catch (e) { dbStatus("error", e.message); }
}

async function openNoteEditor(nodeId, name) {
  try {
    const n = await api(`/api/database/note/${encodeURIComponent(nodeId)}`);
    $("#db-editor").classList.remove("hidden");
    $("#db-editor-title").textContent = `✏️ ${n.entryname} (${n.node_id}) · ${n.version} · ${n.vcl.length} vcl entries`;
    $("#db-editor-content").value = n.content || "";
    $("#db-editor-summary").value = "";
    $("#db-editor").scrollIntoView({ behavior: "smooth" });
  } catch (e) { dbStatus("error", e.message); }
}

async function saveNoteEditor() {
  const title = $("#db-editor-title").textContent;
  const m = title.match(/\(([^)]+)\)/);
  if (!m) return;
  const nodeId = m[1].trim();
  const summary = $("#db-editor-summary").value.trim() || "Updated via web UI.";
  try {
    const r = await api("/api/database/note/update", {
      method: "POST",
      body: { node_id: nodeId, content: $("#db-editor-content").value, summary },
    });
    dbStatus("done", `saved ${r.note.entryname} v${r.note.version}`);
    $("#db-editor").classList.add("hidden");
    loadDbNotes(); loadDbProjects();
  } catch (e) { dbStatus("error", e.message); }
}

$("#btn-db-open").addEventListener("click", async () => {
  const name = $("#db-project-select").value;
  if (!name) return;
  const merge = $("#db-merge-check")?.checked ?? false;
  try {
    const r = await api("/api/database/open", {
      method: "POST",
      body: { name, replace: !merge },
    });
    dbStatus("done", `opened ${r.project.name}: ${r.nodes} nodes · ${r.edges} edges`
      + (r.replaced ? " (graph replaced)" : " (merged)"));
    loadDbNotes(); refreshSummary(); refreshNodes(); loadGraph(); loadDbColors();
  } catch (e) { dbStatus("error", e.message); }
});

$("#btn-db-create").addEventListener("click", async () => {
  const name = $("#db-create-name").value.trim();
  if (!name) { dbStatus("error", "project name required"); return; }
  try {
    await api("/api/database/create", { method: "POST",
      body: { name, description: $("#db-create-desc").value.trim() } });
    $("#db-create-name").value = "";
    dbStatus("done", `created project "${name}"`);
    loadDbProjects();
  } catch (e) { dbStatus("error", e.message); }
});

$("#btn-db-sync").addEventListener("click", async () => {
  dbStatus("running", "exporting graph nodes → .md notes…");
  try {
    const r = await api("/api/database/sync", { method: "POST", body: {} });
    dbStatus("done", `exported: ${r.created} created, ${r.updated} updated`);
    loadDbNotes(); loadDbProjects();
  } catch (e) { dbStatus("error", e.message); }
});

$("#btn-db-refresh").addEventListener("click", () => { loadDbProjects(); loadDbNotes(); });
$("#btn-db-save").addEventListener("click", saveNoteEditor);
$("#btn-db-cancel").addEventListener("click", () => $("#db-editor").classList.add("hidden"));

// ── database tab — supplements (opt-in graph overlays) ──────────────────────
$("#btn-db-supp-open").addEventListener("click", async () => {
  const slug = $("#db-supplement-select").value;
  const proj = $("#db-project-select")?.value || "";
  if (!slug) { dbStatus("error", "select a supplement first"); return; }
  try {
    const r = await api("/api/database/supplement/open", {
      method: "POST", body: { supplement: slug, project: proj } });
    dbStatus("done", `supplement "${r.supplement}" open: +${r.loaded} nodes · +${r.edges_loaded} edges`);
    loadDbNotes(); loadDbSupplements(); refreshSummary(); refreshNodes(); loadGraph(); loadDbColors();
  } catch (e) { dbStatus("error", e.message); }
});

$("#btn-db-supp-close").addEventListener("click", async () => {
  let slug = $("#db-supplement-select").value;
  const proj = $("#db-project-select")?.value || "";
  if (!slug) {
    // fallback: close the first ACTIVE supplement (selection may have reset)
    try {
      const r = await api(`/api/database/supplements?project=${encodeURIComponent(proj)}`);
      const act = (r.supplements || []).find((s) => s.active);
      slug = act ? act.slug : "";
    } catch (e) { /* keep empty */ }
  }
  if (!slug) { dbStatus("error", "select a supplement first"); return; }
  try {
    const r = await api("/api/database/supplement/close", {
      method: "POST", body: { supplement: slug, project: proj } });
    dbStatus("done", `supplement "${r.supplement}" closed: removed ${r.removed_nodes} nodes · ${r.removed_edges} edges`);
    loadDbNotes(); loadDbSupplements(); refreshSummary(); refreshNodes(); loadGraph(); loadDbColors();
  } catch (e) { dbStatus("error", e.message); }
});

$("#btn-db-supp-create").addEventListener("click", async () => {
  const name = $("#db-supp-create-name").value.trim();
  const proj = $("#db-project-select")?.value || "";
  if (!name) { dbStatus("error", "supplement name required"); return; }
  if (!proj) { dbStatus("error", "select a project first"); return; }
  try {
    await api("/api/database/supplement/create", { method: "POST",
      body: { name, description: $("#db-supp-create-desc").value.trim(), project: proj } });
    $("#db-supp-create-name").value = "";
    dbStatus("done", `created supplement "${name}" in "${proj}"`);
    loadDbSupplements();
  } catch (e) { dbStatus("error", e.message); }
});

// ── utilities ───────────────────────────────────────────────────────────────
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

$("#btn-refresh").addEventListener("click", () => {
  refreshSummary(); refreshNodes(); loadGraph(); refreshRuns();
});
$("#btn-rebuild").addEventListener("click", async () => {
  $("#health-line").textContent = "rebuilding graph from assets/…";
  try {
    await api("/api/graph/rebuild", { method: "POST", body: {} });
    $("#health-line").textContent = "rebuilt ✓";
    refreshSummary(); refreshNodes(); loadGraph();
  } catch (e) { $("#health-line").textContent = "rebuild failed: " + e.message; }
});

// expose for inline onclick handlers
window.selectNode = selectNode;
window.addEventListener("DOMContentLoaded", () => {
  setupCanvasInteractions();
  boot();
});
