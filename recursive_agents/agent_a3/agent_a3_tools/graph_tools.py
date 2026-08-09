"""
agent_a1_tools.graph_tools — Knowledge Graph tools (8 tools)

get_local_graph, search_graph_nodes, read_node, validate_graph,
summarize_local, list_projects, project_info, register_node, link_nodes
"""
from __future__ import annotations
from typing import Any
from .tool_base import ReadOnlyTool, ToolContext, ToolResult


class GetLocalGraphTool(ReadOnlyTool):
    tool_name = "get_local_graph"
    category = "graph"
    description = "Materialize the local graph around a node (depth 3)."
    tool_schema = {
        "type": "object", "required": ["node_id"],
        "properties": {
            "node_id": {"type": "string", "description": "Anchor node ID."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        node_id = args.get("node_id", "")
        if tk and tk.graph:
            try:
                local = tk.graph.materialize_local(node_id, 3)
                return ToolResult.success(
                    local.verbalize(max_nodes=40, max_edges=50),
                    node_id=node_id)
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success("(graph not available)", node_id=node_id)


class ReadNodeTool(ReadOnlyTool):
    tool_name = "read_node"
    category = "graph"
    description = "Read a knowledge graph node by ID."
    tool_schema = {
        "type": "object", "required": ["node_id"],
        "properties": {"node_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        node_id = args.get("node_id", "")
        tk = ctx.agent
        if tk and tk.graph:
            try:
                node = tk.graph.get_node(node_id)
                if node:
                    return ToolResult.success(
                        f"{node.entryname} ({node.node_id})",
                        entryname=node.entryname, node_id=node.node_id)
                return ToolResult.fail(f"Node not found: {node_id!r}")
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success(f"(graph not available for {node_id})", node_id=node_id)


class ValidateGraphTool(ReadOnlyTool):
    tool_name = "validate_graph"
    category = "graph"
    description = "Validate the knowledge graph integrity."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        if tk and tk.graph:
            try:
                ok = tk.graph.validate()
                return ToolResult.success(f"Graph valid: {ok}", valid=ok)
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success("(graph not available)")


class SummarizeLocalTool(ReadOnlyTool):
    tool_name = "summarize_local"
    category = "graph"
    description = "Summarize the local graph around a node."
    tool_schema = {
        "type": "object", "required": ["node_id"],
        "properties": {"node_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        node_id = args.get("node_id", "")
        tk = ctx.agent
        if tk and tk.graph:
            try:
                local = tk.graph.materialize_local(node_id, 2)
                return ToolResult.success(
                    local.verbalize(max_nodes=20, max_edges=30),
                    node_id=node_id)
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success("(graph not available)", node_id=node_id)


class ListProjectsTool(ReadOnlyTool):
    tool_name = "list_projects"
    category = "graph"
    description = "List all projects in the knowledge graph."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        if tk and tk.graph:
            try:
                projects = tk.graph.list_projects()
                return ToolResult.success(
                    "\n".join(projects) if projects else "(no projects)",
                    count=len(projects))
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success("(graph not available)")


class ProjectInfoTool(ReadOnlyTool):
    tool_name = "project_info"
    category = "graph"
    description = "Get information about a project."
    tool_schema = {
        "type": "object", "required": ["project_id"],
        "properties": {"project_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        pid = args.get("project_id", "")
        tk = ctx.agent
        if tk and tk.graph:
            try:
                info = tk.graph.project_info(pid)
                return ToolResult.success(str(info), project_id=pid)
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success(f"(graph not available for {pid})")


class RegisterNodeTool(ReadOnlyTool):
    tool_name = "register_node"
    category = "graph"
    description = "Register a node in the knowledge graph."
    tool_schema = {
        "type": "object", "required": ["entryname", "node_type"],
        "properties": {
            "entryname": {"type": "string"},
            "node_type": {"type": "string"},
            "metadata": {"type": "object"},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        if tk and tk.graph:
            try:
                nid = tk.graph.add_node(
                    args.get("entryname", ""),
                    args.get("node_type", "generic"),
                    args.get("metadata", {}))
                return ToolResult.success(f"Registered: {nid}", node_id=nid)
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success("(graph not available — node not persisted)")


class LinkNodesTool(ReadOnlyTool):
    tool_name = "link_nodes"
    category = "graph"
    description = "Link two nodes in the knowledge graph."
    tool_schema = {
        "type": "object", "required": ["source", "target", "edge_type"],
        "properties": {
            "source": {"type": "string"},
            "target": {"type": "string"},
            "edge_type": {"type": "string"},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        if tk and tk.graph:
            try:
                tk.graph.add_edge(args["source"], args["target"],
                                 args["edge_type"])
                return ToolResult.success(
                    f"Linked {args['source']} → {args['target']} ({args['edge_type']})")
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success("(graph not available)")


def register_graph_tools(toolkit) -> None:
    toolkit.register_many([
        GetLocalGraphTool(), ReadNodeTool(), ValidateGraphTool(),
        SummarizeLocalTool(), ListProjectsTool(), ProjectInfoTool(),
        RegisterNodeTool(), LinkNodesTool(),
    ])
