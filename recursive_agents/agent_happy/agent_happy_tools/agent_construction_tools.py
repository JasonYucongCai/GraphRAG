"""
agent_a1_tools.agent_construction_tools — The 8 Agent Construction Tools

These are the REAL tools with which agent_a1 thinks, evaluates, and
self-acts to build the next recursive agent. They write files on disk,
construct IPP nodes through Γ, verify invariants, test the pipeline,
and deploy into the chain.

agent_plan      — THINK: deterministic construction plan
agent_generate  — GENERATE: render templates → folders on disk
agent_create    — CREATE: Γ-construct + verify 17 invariants
agent_evaluate  — EVALUATE: invariants + audit + channel surface
agent_test      — TEST: pipeline through envelopes → feedback
agent_improve   — IMPROVE: test → patch → retest
agent_deploy    — DEPLOY: generate + construct + register
agent_status    — STATUS: report the chain
"""
from __future__ import annotations

import importlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from .tool_base import BaseTool, ToolContext, ToolResult


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _agent_name(agent_id: str) -> str:
    if agent_id.startswith("agent_"):
        return agent_id
    return f"agent_{agent_id}"

def _level_of(name: str) -> int:
    m = re.search(r"agent_a(\d+)", name)
    return int(m.group(1)) if m else 1

def _render(text: str, **vars_) -> str:
    """Template variable substitution for IPP.json and .md files ONLY.

    DO NOT call this on Python source files — it will corrupt f-strings
    by replacing {agent_id} etc. inside code. For .py files use _sub_py."""
    for k, v in vars_.items():
        # Replace __KEY__ format (uppercase, double underscore)
        text = text.replace(f"__{k.upper()}__", str(v))
        # Replace {key} format (lowercase, curly braces)
        text = text.replace("{" + k + "}", str(v))
    return text


def _sub_py(text: str, src_agent: str, dst_agent: str,
            src_level: int, dst_level: int) -> str:
    """Safe Python source substitution — replaces concrete strings only,
    NEVER touches f-string template variables like {agent_id}."""
    # Longest patterns first to avoid partial matches
    text = text.replace(f"{src_agent}_engine", f"{dst_agent}_engine")
    text = text.replace(f"{src_agent}_tools", f"{dst_agent}_tools")
    text = text.replace(src_agent, dst_agent)
    text = text.replace(f"level {src_level}", f"level {dst_level}")
    text = text.replace(f"Level {src_level}", f"Level {dst_level}")
    return text


def _sub_doc(text: str, src_agent: str, dst_agent: str,
             src_level: int, dst_level: int,
             engine_pkg: str, tools_pkg: str,
             generated_by: str) -> str:
    """Safe .md documentation substitution — concrete strings only."""
    text = _sub_py(text, src_agent, dst_agent, src_level, dst_level)
    # Also handle package paths
    src_pkg = f"recursive_agents.{src_agent}"
    dst_pkg = f"recursive_agents.{dst_agent}"
    text = text.replace(src_pkg, dst_pkg)
    text = text.replace(f"{src_pkg}.{src_agent}_engine", engine_pkg)
    text = text.replace(f"{src_pkg}.{src_agent}_tools", tools_pkg)
    # Apply template vars for remaining {var} patterns in docs
    text = _render(
        text,
        agent_id=dst_agent,
        engine_pkg=engine_pkg,
        tools_pkg=tools_pkg,
        level=str(dst_level),
        generated_by=generated_by,
        log_dir="recursive_agents/graph_data/logs/IPP",
    )
    return text

# Path to runtime templates
_TEMPLATES = Path(__file__).resolve().parents[2] / "runtime" / "templates"


# ══════════════════════════════════════════════════════════════════════
# 1. agent_plan
# ══════════════════════════════════════════════════════════════════════

class AgentPlanTool(BaseTool):
    tool_name = "agent_plan"
    category = "agent_construction"
    description = (
        "THINK: Produce the deterministic construction plan for the next "
        "recursive agent. Returns the agent_id, level, step sequence, and "
        "target folder paths. This is the FIRST step — the agent must call "
        "this before any other construction tool."
    )
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent ID (e.g. 'a2' or 'agent_a2')"},
            "level": {"type": "integer", "description": "Level number (default: auto-detect)"},
        },
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        agent_id = _agent_name(args.get("agent_id", ""))
        level = int(args.get("level") or _level_of(agent_id))
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        plan = {
            "agent_id": agent_id,
            "level": level,
            "steps": [
                "agent_generate", "agent_create", "agent_evaluate",
                "agent_test", "agent_improve", "agent_deploy",
                "agent_status",
            ],
            "target_folders": {
                "agent": str(root / agent_id),
                "engine": str(root / agent_id / f"{agent_id}_engine"),
                "tools": str(root / agent_id / f"{agent_id}_tools"),
            },
            "verification_required": [
                "TOOL_COUNT >= 50",
                "RECURSIVE_CAPABILITY (8 construction tools)",
                "ENGINE_COMPREHENSIVENESS (hooks, prompt, autopilot, summarizer)",
                "ALL 17 IPP INVARIANTS",
                "AUDIT CHAINS INTACT",
                "README.md in agent/, engine/, tools/",
            ],
        }
        return ToolResult.success(
            f"Plan for {agent_id} (level {level}): "
            + " → ".join(plan["steps"]),
            agent_id=agent_id, level=level, steps=plan["steps"],
            target_folders=plan["target_folders"],
            verification_required=plan["verification_required"],
        )


# ══════════════════════════════════════════════════════════════════════
# 2. agent_generate
# ══════════════════════════════════════════════════════════════════════

class AgentGenerateTool(BaseTool):
    tool_name = "agent_generate"
    category = "agent_construction"
    description = (
        "GENERATE: Write the next recursive agent's engine + tools folders "
        "from the templates. This is REAL filesystem work — the files appear "
        "on disk. The agent's own hands do this, not a bootstrap script. "
        "Writes: IPP.json, IPP_object.py, IPP_executor.py, README.md, "
        "system_prompt.md, __init__.py for each folder."
    )
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent ID"},
            "level": {"type": "integer", "description": "Level number"},
        },
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        agent_id = _agent_name(args.get("agent_id", ""))
        level = int(args.get("level") or _level_of(agent_id))
        generated_by = tk.agent_id if tk else "agent_a1"

        # Compute paths
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        agent_dir = root / agent_id
        engine_dir = agent_dir / f"{agent_id}_engine"
        tools_dir = agent_dir / f"{agent_id}_tools"
        engine_pkg = f"recursive_agents.{agent_id}.{agent_id}_engine"
        tools_pkg = f"recursive_agents.{agent_id}.{agent_id}_tools"

        # Template files to render
        template_files = {
            "engine_IPP.json": (engine_dir / "IPP.json", "engine"),
            "engine_IPP_object.py": (engine_dir / "IPP_object.py", "engine"),
            "engine_IPP_executor.py": (engine_dir / "IPP_executor.py", "engine"),
            "tools_IPP.json": (tools_dir / "IPP.json", "tools"),
            "tools_IPP_object.py": (tools_dir / "IPP_object.py", "tools"),
            "tools_IPP_executor.py": (tools_dir / "IPP_executor.py", "tools"),
            "README_agent.md": (agent_dir / "README.md", "agent"),
            "README_engine.md": (engine_dir / "README.md", "engine"),
            "README_tools.md": (tools_dir / "README.md", "tools"),
            "system_prompt.md": (agent_dir / "system_prompt.md", "agent"),
        }

        written = []
        for tpl_name, (target, kind) in template_files.items():
            tpl_path = _TEMPLATES / tpl_name
            if not tpl_path.exists():
                continue
            text = tpl_path.read_text(encoding="utf-8")
            rendered = _render(
                text,
                agent_id=agent_id,
                node_id=f"{agent_id}_{kind}",
                engine_pkg=engine_pkg,
                tools_pkg=tools_pkg,
                level=str(level),
                generated_by=generated_by,
                log_dir="recursive_agents/graph_data/logs/IPP",
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            written.append(str(target.relative_to(root)))

        # ── INHERITANCE ──
        # Copy the generating agent's engine + tool files so the new agent
        # inherits the full capabilities (agents are of equal level).
        self._inherit_engine(tk, engine_dir, agent_id, level, generated_by, root, written)
        self._inherit_tools(tk, tools_dir, agent_id, level, generated_by, root, written)

        # ── DOCUMENTATION INHERITANCE ──
        # Overwrite template READMEs, system_prompt, and __init__.py files
        # with agent_a1's RICH versions (name-substituted). Agent a2 must
        # be an IMPROVEMENT, not a downgrade.
        self._inherit_docs(tk, agent_dir, engine_dir, tools_dir,
                          agent_id, level, generated_by, root, written)

        # Validate generated IPP.json files
        try:
            json.loads((engine_dir / "IPP.json").read_text(encoding="utf-8"))
            json.loads((tools_dir / "IPP.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return ToolResult.fail(f"Generated IPP.json is invalid JSON: {e}",
                                   agent_id=agent_id, level=level)

        return ToolResult.success(
            f"Generated {agent_id} (level {level}): {len(written)} files written by {generated_by}",
            agent_id=agent_id, level=level, generated_by=generated_by,
            files_written=len(written), files=written,
            folders={
                "agent": str(agent_dir),
                "engine": str(engine_dir),
                "tools": str(tools_dir),
            },
        )

    def _inherit_engine(self, tk, engine_dir: Path, agent_id: str, level: int,
                        generated_by: str, root: Path, written: list) -> None:
        """Copy engine enhancement files BYTE-FOR-BYTE from the generating agent.

        Python source files are copied verbatim — NO template substitution.
        Agents are equal level; the code is structurally identical.
        """
        if tk is None:
            return
        source_engine_dir = root / tk.agent_id / f"{tk.agent_id}_engine"
        if not source_engine_dir.exists():
            return

        inherit_files = [
            "engine.py", "hooks.py", "prompt_assembler.py",
            "autopilot.py", "summarizer.py",
        ]
        for fn in inherit_files:
            src = source_engine_dir / fn
            if src.exists():
                dst = engine_dir / fn
                text = src.read_text(encoding="utf-8")
                engine_dir.mkdir(parents=True, exist_ok=True)
                dst.write_text(text, encoding="utf-8")  # byte-for-byte copy
                written.append(str(dst.relative_to(root)))

    def _inherit_tools(self, tk, tools_dir: Path, agent_id: str, level: int,
                       generated_by: str, root: Path, written: list) -> None:
        """Copy tool files BYTE-FOR-BYTE from the generating agent.

        Python source files are copied verbatim — NO template substitution.
        Agents are equal level; the tool code is structurally identical.
        """
        if tk is None:
            return

        source_tools_dir = root / tk.agent_id / f"{tk.agent_id}_tools"
        if not source_tools_dir.exists():
            return

        inherit_files = [
            "tool_base.py", "tool_registry.py",
            "agent_construction_tools.py",
            "file_tools.py", "search_tools.py", "terminal_tools.py",
            "memory_tools.py", "graph_tools.py", "ipp_tools.py",
            "llm_tools.py", "evaluation_tools.py", "documentation_tools.py",
            "log_tools.py", "web_tools.py", "system_tools.py",
            "powershell_tools.py", "code_tools.py",
        ]

        for fn in inherit_files:
            src = source_tools_dir / fn
            if src.exists():
                dst = tools_dir / fn
                text = src.read_text(encoding="utf-8")
                tools_dir.mkdir(parents=True, exist_ok=True)
                dst.write_text(text, encoding="utf-8")  # byte-for-byte copy
                written.append(str(dst.relative_to(root)))

    def _inherit_docs(self, tk, agent_dir: Path, engine_dir: Path,
                      tools_dir: Path, agent_id: str, level: int,
                      generated_by: str, root: Path, written: list) -> None:
        """Copy RICH documentation from the generating agent, safely
        substituting agent names WITHOUT corrupting Python f-strings.

        - .py __init__.py: _sub_py (concrete string replace only, no {var} touching)
        - .md README/prompt: _sub_doc (concrete replace + safe template vars)
        """
        if tk is None:
            return

        source_agent = tk.agent_id
        source_level = _level_of(source_agent)
        source_root = root / source_agent
        source_engine_dir = source_root / f"{source_agent}_engine"
        source_tools_dir = source_root / f"{source_agent}_tools"

        engine_pkg = f"recursive_agents.{agent_id}.{agent_id}_engine"
        tools_pkg = f"recursive_agents.{agent_id}.{agent_id}_tools"

        # ── __init__.py (Python: _sub_py only — no _render on .py!) ──
        init_map = {
            source_root / "__init__.py": agent_dir / "__init__.py",
            source_engine_dir / "__init__.py": engine_dir / "__init__.py",
            source_tools_dir / "__init__.py": tools_dir / "__init__.py",
        }
        for src_path, dst_path in init_map.items():
            if src_path.exists():
                text = src_path.read_text(encoding="utf-8")
                rendered = _sub_py(text, source_agent, agent_id,
                                  source_level, level)
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_text(rendered, encoding="utf-8")
                written.append(str(dst_path.relative_to(root)))

        # ── README.md (Markdown: _sub_doc — safe for non-Python) ──
        readme_map = {
            source_root / "README.md": agent_dir / "README.md",
            source_engine_dir / "README.md": engine_dir / "README.md",
            source_tools_dir / "README.md": tools_dir / "README.md",
        }
        for src_path, dst_path in readme_map.items():
            if src_path.exists():
                text = src_path.read_text(encoding="utf-8")
                rendered = _sub_doc(
                    text, source_agent, agent_id,
                    source_level, level,
                    engine_pkg, tools_pkg, generated_by,
                )
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_text(rendered, encoding="utf-8")

        # ── system_prompt.md (Markdown) ──
        src_prompt = source_root / "system_prompt.md"
        dst_prompt = agent_dir / "system_prompt.md"
        if src_prompt.exists():
            text = src_prompt.read_text(encoding="utf-8")
            rendered = _sub_doc(
                text, source_agent, agent_id,
                source_level, level,
                engine_pkg, tools_pkg, generated_by,
            )
            dst_prompt.parent.mkdir(parents=True, exist_ok=True)
            dst_prompt.write_text(rendered, encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# 3. agent_create
# ══════════════════════════════════════════════════════════════════════

class AgentCreateTool(BaseTool):
    tool_name = "agent_create"
    category = "agent_construction"
    description = (
        "CREATE: Construct the next agent's engine + tools IPP nodes "
        "through Γ (the 7-step protocol) and verify ALL 17 invariants. "
        "This is the COMPILATION step — the agent is constructed, not copied. "
        "Must call agent_generate first."
    )
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent ID"},
            "level": {"type": "integer", "description": "Level number"},
        },
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        agent_id = _agent_name(args.get("agent_id", ""))
        level = int(args.get("level") or _level_of(agent_id))
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        engine_dir = root / agent_id / f"{agent_id}_engine"
        tools_dir = root / agent_id / f"{agent_id}_tools"

        # Check that generation was done
        if not (engine_dir / "IPP.json").exists():
            return ToolResult.fail(
                f"{agent_id} not generated yet — call agent_generate first",
                agent_id=agent_id)

        try:
            from IPP.IPP_constructor import IPPConstructor
            from IPP.IPP_registry import GraphContext
            from IPP.IPP_verify import verify_node
            from recursive_agents.runtime.engine import (
                RecursiveAgentEngine, RECURSIVE_TOOL_NAMES)

            engine_pkg = f"recursive_agents.{agent_id}.{agent_id}_engine"
            tools_pkg = f"recursive_agents.{agent_id}.{agent_id}_tools"

            engine_exec = importlib.import_module(f"{engine_pkg}.IPP_executor")
            tools_exec = importlib.import_module(f"{tools_pkg}.IPP_executor")

            engine = RecursiveAgentEngine(
                graph=tk.graph if tk else None,
                encoder=tk.encoder if tk else None,
                llm=tk.llm if tk else None,
                agent_id=agent_id, level=level,
                toolkit=tk,
            )
            gctx = GraphContext()
            gctx.bind("engine", engine)
            gctx.bind("toolkit", tk)
            gctx.bind("agent_id", agent_id)
            gctx.bind("tool_names", list(RECURSIVE_TOOL_NAMES))

            # Construct engine node
            gamma_e = IPPConstructor(
                gctx, executor_classes={
                    ch: engine_exec.AgentExecutor
                    for ch in ("ground", "chat", "chat_stream")
                })
            engine_node = gamma_e.construct_file(
                engine_dir / "IPP.json", gctx)
            gamma_e.recall_scope(engine_node)
            gctx.register_node(engine_node)

            # Construct tools node
            ch_map = {}
            if tk:
                for name in tk.tools:
                    ch_map[name] = tools_exec.ToolExecutor
            gamma_t = IPPConstructor(gctx, executor_classes=ch_map)
            tools_node = gamma_t.construct_file(
                tools_dir / "IPP.json", gctx)
            gamma_t.recall_scope(tools_node)
            gctx.register_node(tools_node)

            engine.node = engine_node
            engine._tools_node = tools_node
            engine._ipp_context = gctx

            # Store in toolkit
            tk.constructed[agent_id] = engine

            # Verify
            ev = verify_node(engine_node)
            tv = verify_node(tools_node)

            return ToolResult.success(
                f"{agent_id} constructed: engine_node={engine_node.node_id}, "
                f"tools_node={tools_node.node_id}",
                agent_id=agent_id, level=level,
                engine_node=engine_node.node_id,
                tools_node=tools_node.node_id,
                verified=(not ev and not tv),
                engine_failures=list(ev) if ev else [],
                tools_failures=list(tv) if tv else [],
            )
        except Exception as e:
            return ToolResult.fail(
                f"Construction of {agent_id} failed: {type(e).__name__}: {e}",
                agent_id=agent_id)


# ══════════════════════════════════════════════════════════════════════
# 4. agent_evaluate
# ══════════════════════════════════════════════════════════════════════

class AgentEvaluateTool(BaseTool):
    tool_name = "agent_evaluate"
    category = "agent_construction"
    description = (
        "EVALUATE: Check ALL 17 IPP invariants + audit chains + channel "
        "surface of a constructed agent. Returns pass/fail with details."
    )
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent ID"},
        },
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        agent_id = _agent_name(args.get("agent_id", ""))
        engine = tk.constructed.get(agent_id) if tk else None

        if engine is None:
            return ToolResult.fail(f"{agent_id} not constructed — call agent_create first")

        try:
            from IPP.IPP_verify import verify_node

            ef = verify_node(engine.node)
            tf = verify_node(engine._tools_node)
            audits = (
                all(ex.audit_verify() for ex in engine.node.executors.values())
                and all(ex.audit_verify() for ex in engine._tools_node.executors.values())
            )

            return ToolResult.success(
                f"{agent_id}: {'ALL 17 OK' if (not ef and not tf) else 'FAILED'}",
                agent_id=agent_id,
                ok=(not ef and not tf),
                engine_failures=list(ef) if ef else [],
                tools_failures=list(tf) if tf else [],
                audit_chains=audits,
                engine_channels=list(engine.node.channels) if engine.node else [],
                tools_channels=list(engine._tools_node.channels) if engine._tools_node else [],
            )
        except Exception as e:
            return ToolResult.fail(f"Evaluation failed: {e}")


# ══════════════════════════════════════════════════════════════════════
# 5. agent_test
# ══════════════════════════════════════════════════════════════════════

class AgentTestTool(BaseTool):
    tool_name = "agent_test"
    category = "agent_construction"
    description = (
        "TEST: Run the ground→chat pipeline through the envelopes + latency "
        "probe → structured feedback. The agent must respond with 'OK'."
    )
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent ID"},
        },
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        agent_id = _agent_name(args.get("agent_id", ""))
        engine = tk.constructed.get(agent_id) if tk else None

        if engine is None:
            return ToolResult.fail(f"{agent_id} not constructed")

        feedback = {"agent_id": agent_id, "checks": {}, "issues": []}
        try:
            # Test chat pipeline
            res = engine.node.invoke("ground", {"task": "Reply with OK only"})
            answer = str(res.payload.get("answer", "")) if isinstance(
                res.payload, dict) else str(res.payload)
            ok_ = "OK" in answer
            feedback["checks"]["chat_pipeline"] = ok_
            if not ok_:
                feedback["issues"].append("chat_pipeline: answer missing OK")

            # Test latency
            try:
                latency = int(engine.node.executors["chat"].policy.get(
                    "max_latency_ms", 0))
                feedback["latency_ms"] = latency
                if latency < 600000:
                    feedback["issues"].append(f"latency {latency}ms < 600000ms")
                    feedback["checks"]["latency"] = False
                else:
                    feedback["checks"]["latency"] = True
            except Exception:
                feedback["checks"]["latency"] = False
                feedback["issues"].append("latency probe failed")

            # Test invariants
            from IPP.IPP_verify import verify_node
            ef = verify_node(engine.node)
            tf = verify_node(engine._tools_node)
            feedback["checks"]["invariants"] = (not ef and not tf)
            if ef or tf:
                feedback["issues"].append(f"invariants: {list(ef) if ef else []} / {list(tf) if tf else []}")

            feedback["ok"] = not feedback["issues"]
            return ToolResult.success(
                f"{agent_id} test: ok={feedback['ok']}, issues={len(feedback['issues'])}",
                **feedback)
        except Exception as e:
            return ToolResult.fail(f"Test failed: {e}", agent_id=agent_id)


# ══════════════════════════════════════════════════════════════════════
# 6. agent_improve
# ══════════════════════════════════════════════════════════════════════

class AgentImproveTool(BaseTool):
    tool_name = "agent_improve"
    category = "agent_construction"
    description = (
        "IMPROVE: Test → deterministic patch → reconstruct → retest until "
        "the agent passes. Feedback is logged to "
        "recursive_agents/feedback/{agent_id}.txt"
    )
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent ID"},
            "iterations": {"type": "integer", "description": "Max improvement iterations (default: 3)"},
        },
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        agent_id = _agent_name(args.get("agent_id", ""))
        iterations = int(args.get("iterations") or 3)
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")

        patches = []
        rounds = []
        final = {}

        for i in range(1, max(1, iterations) + 1):
            # Run test
            test_tool = AgentTestTool()
            fb_result = test_tool.invoke({"agent_id": agent_id}, ctx)
            fb = fb_result.metadata
            fb["ok"] = fb_result.ok
            fb["issues"] = fb.get("issues", [])
            rounds.append({"round": i, "ok": fb.get("ok", False),
                          "issues": fb.get("issues", [])})

            if fb.get("ok"):
                final = fb
                break

            # Try to patch
            patch = self._apply_patch(root, agent_id, fb)
            if patch is None:
                final = fb
                break
            patches.append(patch)

            # Reconstruct
            tk.constructed.pop(agent_id, None)
            create_tool = AgentCreateTool()
            create_tool.invoke({"agent_id": agent_id}, ctx)
        else:
            # Final test after all iterations
            test_tool = AgentTestTool()
            final_r = test_tool.invoke({"agent_id": agent_id}, ctx)
            final = final_r.metadata
            final["ok"] = final_r.ok

        # Write feedback
        self._write_feedback(root, agent_id, patches, rounds, final)

        return ToolResult.success(
            f"{agent_id}: {len(rounds)} rounds, {len(patches)} patches, "
            f"final ok={final.get('ok', False)}",
            agent_id=agent_id, iterations=len(rounds),
            patches=patches, rounds=rounds, final=final)

    def _apply_patch(self, root: Path, agent_id: str,
                     feedback: dict) -> Optional[str]:
        f = root / agent_id / f"{agent_id}_engine" / "IPP.json"
        if not f.exists():
            return None
        doc = json.loads(f.read_text(encoding="utf-8"))
        patched = False
        for ch in doc.get("channels", []):
            if ch.get("channel_id") == "chat":
                pol = ch.setdefault("ipp_executor", {}).setdefault("policy", {})
                if int(pol.get("max_latency_ms", 0)) < 600000:
                    pol["max_latency_ms"] = 600000
                    patched = True
        if patched:
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
            return f"chat latency policy → 600000ms"
        return None

    def _write_feedback(self, root: Path, agent_id: str, patches: list,
                        rounds: list, final: dict) -> None:
        d = root / "feedback"
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"# {agent_id} — improvement feedback ({stamp})",
            f"ok: {final.get('ok', False)}",
            f"iterations: {len(rounds)}",
            f"patches: {patches}",
            "rounds:",
        ]
        for r in rounds:
            lines.append(f"  round {r['round']}: ok={r['ok']} issues={r['issues']}")
        (d / f"{agent_id}.txt").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# 7. agent_deploy
# ══════════════════════════════════════════════════════════════════════

class AgentDeployTool(BaseTool):
    tool_name = "agent_deploy"
    category = "agent_construction"
    description = (
        "DEPLOY: Generate + construct + register the agent in the chain. "
        "If not yet generated, does generate + create first. Adds to "
        "the agent chain."
    )
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent ID"},
            "level": {"type": "integer", "description": "Level number"},
        },
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        agent_id = _agent_name(args.get("agent_id", ""))
        level = int(args.get("level") or _level_of(agent_id))

        if agent_id not in tk.constructed:
            # Do full generate + create
            gen_tool = AgentGenerateTool()
            gen_r = gen_tool.invoke({"agent_id": agent_id, "level": level}, ctx)
            if not gen_r.ok:
                return gen_r
            create_tool = AgentCreateTool()
            create_r = create_tool.invoke({"agent_id": agent_id, "level": level}, ctx)
            if not create_r.ok:
                return create_r

        if agent_id not in tk.chain:
            tk.chain.append(agent_id)

        return ToolResult.success(
            f"{agent_id} deployed: chain = {tk.chain}",
            agent_id=agent_id, level=level,
            chain=list(tk.chain),
            constructed=(agent_id in tk.constructed),
        )


# ══════════════════════════════════════════════════════════════════════
# 8. agent_status
# ══════════════════════════════════════════════════════════════════════

class AgentStatusTool(BaseTool):
    tool_name = "agent_status"
    category = "agent_construction"
    description = (
        "STATUS: Report the current state of the constructed agent chain, "
        "including which agents are deployed, their levels, and any issues."
    )
    tool_schema = {
        "type": "object",
        "properties": {},
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        return ToolResult.success(
            f"Chain: {' → '.join(tk.chain) if tk.chain else '(empty)'}",
            ok=True,
            chain=list(tk.chain) if tk else [],
            constructed=sorted(tk.constructed) if tk else [],
            total_tools=tk.count() if hasattr(tk, 'count') else 0,
        )


# ══════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════

def register_construction_tools(toolkit) -> None:
    """Register the 8 agent construction tools."""
    toolkit.register_many([
        AgentPlanTool(),
        AgentGenerateTool(),
        AgentCreateTool(),
        AgentEvaluateTool(),
        AgentTestTool(),
        AgentImproveTool(),
        AgentDeployTool(),
        AgentStatusTool(),
    ])
