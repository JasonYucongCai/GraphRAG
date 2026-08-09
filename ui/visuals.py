"""
ui.visuals — interactive graph visualizations.

Generates self-contained interactive HTML for a KnowledgeGraph, in the spirit
of the PyVis graph the Obsidian notebook produced (`2d_cft_knowledge_graph.html`)
and the exported 低空经济.html from the ScientificInfrastructure:

  • `interactive_html(graph, anchor=None, depth=3)` — a PyVis-style
    force-directed network (vis-network from CDN, draggable, zoomable,
    hover tooltips with descriptions) for any graph or local graph.
  • `mermaid_flowchart(graph)` — the Mermaid `graph LR` dependency diagram
    used throughout the ScientificInfrastructure notebooks.

Both outputs are plain strings you can save to `database/<project>/` or serve.
"""
from __future__ import annotations

import html as _html
import json
import re
from typing import Any, Optional

CAT_COLORS = {
    "subject": "#4caf7d", "paper": "#4c9aff", "concept": "#ffab4c",
    "benchmark": "#b57ff2", "experience": "#ef5350", "note": "#4cc2ff",
}
DEFAULT_COLOR = "#8aa0b0"


def _color_for(category: str, category_colors: Optional[dict] = None) -> str:
    """Resolve a node category to its color. ``category_colors`` is the
    per-project map ``{"default": hex, "map": {category: hex}}`` (see
    database/README.md · categories.json); falls back to the BASE palette."""
    if category_colors:
        cmap = category_colors.get("map") or {}
        if category in cmap:
            return str(cmap[category])
        return str(category_colors.get("default") or DEFAULT_COLOR)
    return CAT_COLORS.get(category, DEFAULT_COLOR)


def _node_payload(graph, node, category_colors: Optional[dict] = None) -> dict:
    return {
        "id": str(node.node_id),
        "label": node.entryname,
        "color": _color_for(node.category, category_colors),
        "category": node.category,
        "description": node.description[:300],
        "title": node.description[:300],   # vis-network hover tooltip
        "in": node.stats.get("in_degree", 0),
        "out": node.stats.get("out_degree", 0),
        "pr": round(node.stats.get("pagerank", 0.0), 4),
    }


def _edge_payload(e) -> dict:
    return {"from": str(e.source), "to": str(e.target), "label": e.relation}


def collect_view(graph, anchor: Optional[Any] = None, depth: int = 3,
                 category_colors: Optional[dict] = None) -> dict:
    """Collect nodes+edges for either the full graph or a local graph."""
    if anchor is not None:
        local = graph.materialize_local(anchor, depth=depth)
        nodes = [_node_payload(graph, n, category_colors) for n in local.nodes.values()]
        edges = [_edge_payload(e) for e in local.edges]
        anchor_id = str(anchor)
    else:
        nodes = [_node_payload(graph, n, category_colors) for n in graph._nodes.values()]
        edges = [_edge_payload(e) for e in graph._edges.values()]
        anchor_id = None
    return {"nodes": nodes, "edges": edges, "anchor": anchor_id}


def interactive_html(graph, anchor: Optional[Any] = None, depth: int = 3,
                     title: str = "Graph Knowledge Network",
                     category_colors: Optional[dict] = None) -> str:
    """
    PyVis-style interactive network (vis-network CDN), self-contained HTML.

    Mirrors the Obsidian notebook's interactive graph: force-directed physics,
    draggable nodes, zoom/pan, hover tooltips with node descriptions.
    ``category_colors`` = per-project ``{default, map}`` (categories.json).
    """
    view = collect_view(graph, anchor, depth, category_colors)
    nodes_json = json.dumps(view["nodes"], ensure_ascii=False)
    edges_json = json.dumps(view["edges"], ensure_ascii=False)
    anchor_id = json.dumps(view["anchor"])
    colors = category_colors or {"default": DEFAULT_COLOR, "map": CAT_COLORS}
    legend = "".join(
        f'<div class="lg"><span class="sw" style="background:{c}"></span>{k}</div>'
        for k, c in sorted(colors.get("map", {}).items()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{_html.escape(title)} — interactive graph</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  html, body, #graph {{ height: 100%; margin: 0; background: #101418; font-family: Segoe UI, system-ui, sans-serif; }}
  #graph {{ height: calc(100% - 48px); }}
  header {{ height: 48px; display: flex; align-items: center; gap: 14px; padding: 0 18px;
           background: #161c22; color: #dbe4ec; border-bottom: 1px solid #2a3642; }}
  header h1 {{ font-size: 15px; margin: 0; }}
  header span {{ color: #8aa0b0; font-size: 12px; font-family: Consolas, monospace; }}
  #legend {{ display: flex; gap: 12px; margin-left: auto; font-size: 11px; }}
  .lg {{ display: flex; align-items: center; gap: 5px; }}
  .sw {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
</style>
</head>
<body>
<header>
  <h1>⬡ {_html.escape(title)}</h1>
  <span id="stats"></span>
  <div id="legend">
    {legend}
  </div>
</header>
<div id="graph"></div>
<script>
const nodes = new vis.DataSet({nodes_json});
const edges = new vis.DataSet({edges_json});
const container = document.getElementById('graph');
const options = {{
  nodes: {{ shape: 'dot', size: 12, font: {{ color: '#dbe4ec', size: 12 }},
           borderWidth: 2, shadow: true }},
  edges: {{ arrows: {{ to: {{ enabled: true, scaleFactor: 0.6 }} }},
           color: {{ color: '#3a4a58', highlight: '#4cc2ff' }},
           font: {{ color: '#8aa0b0', size: 10, strokeWidth: 0 }},
           smooth: {{ type: 'continuous' }} }},
  physics: {{
    forceAtlas2Based: {{ gravitationalConstant: -60, centralGravity: 0.01,
                        springLength: 140, springConstant: 0.08, damping: 0.4 }},
    solver: 'forceAtlas2Based', stabilization: {{ iterations: 250 }},
    maxVelocity: 40, timestep: 0.4
  }},
  interaction: {{ hover: true, tooltipDelay: 120, dragNodes: true,
                  dragView: true, zoomView: true, multiselect: false }},
  groups: {{}}
}};
const network = new vis.Network(container, {{ nodes, edges }}, options);
const anchor = {anchor_id};
if (anchor) {{
  network.once('stabilizationIterationsDone', () => {{
    network.focus(anchor, {{ scale: 1.15, animation: {{ duration: 600 }} }});
  }});
}}
document.getElementById('stats').textContent =
  `${{nodes.length}} nodes · ${{edges.length}} edges` +
  (anchor ? ` · focused on ${{anchor}}` : ' · global view');
network.on('click', (p) => {{
  if (p.nodes && p.nodes.length) {{
    const n = nodes.get(p.nodes[0]);
    // tell the parent SPA to open its detail drawer (no alert popups)
    if (window.parent && window.parent !== window) {{
      window.parent.postMessage(
        {{ type: 'graph-node-click', nodeId: n.id }}, '*');
    }}
  }}
}});
</script>
</body>
</html>"""


def mermaid_flowchart(graph, anchor: Optional[Any] = None, depth: int = 3) -> str:
    """
    Mermaid `graph LR` dependency diagram — the format used throughout the
    ScientificInfrastructure notebooks.
    """
    if anchor is not None:
        local = graph.materialize_local(anchor, depth=depth)
        pairs = [(e.source, e.target, e.relation) for e in local.edges]
    else:
        pairs = [(e.source, e.target, e.relation) for e in graph._edges.values()]

    lines = ["```mermaid", "graph LR"]
    seen: set[str] = set()
    for s, t, rel in pairs:
        sn = _mm(graph, s)
        tn = _mm(graph, t)
        key = f"{sn}|{tn}"
        if key in seen:
            continue
        seen.add(key)
        lines.append(f'    {sn} --"{rel}"--> {tn}')
    lines.append("```")
    return "\n".join(lines)


def _mm(graph, nid) -> str:
    node = graph.get_node(nid)
    name = node.entryname if node else str(nid)
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)[:40] or "node"
    return safe
