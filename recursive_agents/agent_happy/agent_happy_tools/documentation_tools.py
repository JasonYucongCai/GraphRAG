"""
agent_a1_tools.documentation_tools — Documentation generation (4 tools)

write_readme, write_system_prompt, generate_docs, read_docs
"""
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any
from .tool_base import EditTool, ReadOnlyTool, ToolContext, ToolResult


class WriteReadmeTool(EditTool):
    tool_name = "write_readme"
    category = "documentation"
    description = "Write a README.md file for an agent, engine, or tools folder."
    tool_schema = {
        "type": "object", "required": ["target_path", "content"],
        "properties": {
            "target_path": {"type": "string", "description": "Path to the folder to write README.md in."},
            "content": {"type": "string", "description": "Markdown content for the README."},
            "agent_id": {"type": "string", "description": "Agent ID for template variables."},
            "level": {"type": "number", "description": "Agent level."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        target = args.get("target_path", "")
        content = args.get("content", "")
        if not target or not content:
            return ToolResult.fail("target_path and content are required")
        try:
            p = Path(target)
            if p.is_dir():
                p = p / "README.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult.success(f"Written: {p}", path=str(p))
        except Exception as e:
            return ToolResult.fail(str(e))


class WriteSystemPromptTool(EditTool):
    tool_name = "write_system_prompt"
    category = "documentation"
    description = "Write a system_prompt.md file for an agent."
    tool_schema = {
        "type": "object", "required": ["agent_path", "content"],
        "properties": {
            "agent_path": {"type": "string", "description": "Path to the agent folder."},
            "content": {"type": "string", "description": "System prompt content."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_path = args.get("agent_path", "")
        content = args.get("content", "")
        if not agent_path or not content:
            return ToolResult.fail("agent_path and content are required")
        try:
            p = Path(agent_path) / "system_prompt.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult.success(f"Written: {p}", path=str(p))
        except Exception as e:
            return ToolResult.fail(str(e))


class GenerateDocsTool(ReadOnlyTool):
    tool_name = "generate_docs"
    category = "documentation"
    description = "Generate documentation for all agents in the chain."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        docs = []
        for name in (tk.chain if tk else []):
            agent_dir = root / name
            if agent_dir.exists():
                readme = agent_dir / "README.md"
                docs.append(f"## {name}\n"
                           f"- README: {'exists' if readme.exists() else 'MISSING'}\n"
                           f"- Engine: {(agent_dir / f'{name}_engine').exists()}\n"
                           f"- Tools: {(agent_dir / f'{name}_tools').exists()}\n")
        return ToolResult.success("\n".join(docs) if docs else "(no agents in chain)",
                                  agent_count=len(docs))


class ReadDocsTool(ReadOnlyTool):
    tool_name = "read_docs"
    category = "documentation"
    description = "Read documentation for a specific agent."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        tk = ctx.agent
        root = Path(tk.ws_root) / "recursive_agents" / agent_id if tk else Path(".")
        if not root.exists():
            return ToolResult.fail(f"Agent {agent_id} not found")
        docs = {}
        for kind in ["README.md", "system_prompt.md",
                     f"{agent_id}_engine/README.md",
                     f"{agent_id}_tools/README.md"]:
            p = root / kind
            if p.exists():
                try:
                    docs[kind] = p.read_text(encoding="utf-8")[:500]
                except Exception:
                    docs[kind] = "(error reading)"
        return ToolResult.success(
            json.dumps({k: v[:200] for k, v in docs.items()},
                      ensure_ascii=False, indent=2),
            agent_id=agent_id, doc_count=len(docs))


def register_documentation_tools(toolkit) -> None:
    toolkit.register_many([
        WriteReadmeTool(), WriteSystemPromptTool(),
        GenerateDocsTool(), ReadDocsTool(),
    ])
