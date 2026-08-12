"""
recursive_agents.runtime.toolkit — the REAL tool suite of agent_a1 (and of
every constructed agent). Sync port of the Copilot tool architecture
(assets/copilot_agent_tools): BaseTool subclasses with the four-phase
lifecycle + a per-agent registry.

The AGENT-CONSTRUCTION tools (agent_plan / agent_generate / agent_create
/ agent_evaluate / agent_test / agent_improve / agent_deploy /
agent_status) are REAL filesystem tools: agent_generate literally writes
the next agent's engine + tools folders (rendering the templates itself),
agent_create constructs its IPP nodes through Γ, etc. — there is no
compiler cheat: the agent's own tools do the work.

The registry is per-agent (not global): each agent owns its tool
instances; the IPP tools node exposes them as channels (router) and the
LLM sees their definitions via list/describe.
"""
from __future__ import annotations

import importlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

# ══════════════════════════════════════════════════════════════════════
# BaseTool — the four-phase lifecycle (sync port of tool_base.py)
# ══════════════════════════════════════════════════════════════════════
class ToolResult:
    """Structured output envelope for every tool invocation.

    Fields:
        ok: bool — whether the tool executed successfully
        content: str — the tool's output (truncated at 2000 chars by the engine)
        error: Optional[str] — error message when ok=False
        metadata: dict — extra context (timing, agent, file info, etc.)
    """
    def __init__(self, ok: bool = True, content: str = "",
                 error: Optional[str] = None, **meta):
        self.ok = ok
        self.content = content
        self.error = error
        self.metadata = meta

    @staticmethod
    def success(content: str = "", **meta) -> "ToolResult":
        # the report dicts carry "ok" — never forward it twice
        meta.pop("ok", None)
        return ToolResult(True, content, None, **meta)

    @staticmethod
    def fail(message: str, **meta) -> "ToolResult":
        meta.pop("ok", None)
        return ToolResult(False, "", message, **meta)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "content": self.content,
                "error": self.error, "metadata": self.metadata}


class ToolContext:
    """Per-invocation context passed to every tool.

    Fields:
        workspace_root: str — absolute path to the workspace root
        agent: Any — back-reference to the owning agent toolkit
        extra: dict — additional context (session, graph, encoder, etc.)
    """
    def __init__(self, workspace_root: str = "", agent: Any = None,
                 **extra):
        self.workspace_root = workspace_root
        self.agent = agent
        self.extra = extra


class BaseTool:
    """Abstract base for all recursive agent tools.

    Four-phase lifecycle:
        1. _run(args, ctx) — the entry point (catches exceptions)
        2. invoke(args, ctx) — the actual tool logic (override in subclass)
        3. definition() — the JSON-Schema tool definition the LLM sees
        4. register(toolkit) — self-registers into an AgentToolkit

    Every tool has a tool_name, tool_schema, category, and description.
    """
    tool_name: str = "unnamed"
    tool_schema: dict = {"type": "object", "properties": {}}
    category: str = "general"
    description: str = ""

    def definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description or self.tool_name,
                "parameters": self.tool_schema,
            },
        }

    def _run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            return self.invoke(args, ctx)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(f"{type(exc).__name__}: {exc}")

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        raise NotImplementedError


class AgentToolkit:
    """Per-agent tool registry + recursive agent construction machinery.

    Each recursive agent (a1, a2, a3, …) gets its own toolkit instance.
    The toolkit holds the agent's tool definitions (agent_plan, agent_generate,
    agent_create, agent_evaluate, agent_test, agent_improve, agent_deploy,
    agent_status) and the AgentCompiler that builds the next-level agent.

    Key state:
        tools: dict[str, BaseTool] — registered tools by name
        constructed: dict[str, Any] — agent_aX → engine (already built)
        chain: list[str] — the ordered chain of agent IDs (a1, a2, …)
    """

    # ── template files (same source the tools render) ─────────────────────
    TEMPLATES = Path(__file__).resolve().parent / "templates"
    LOG_DIR = "recursive_agents/graph_data/logs/IPP"

    def __init__(self, agent_id: str, root: Optional[Path] = None,
                 ws_root: str = "", graph=None, encoder=None, llm=None):
        """Initialize the toolkit for one recursive agent level.

        Args:
            agent_id: e.g. "agent_a1", "agent_a2"
            root: root path for the recursive_agents folder
            ws_root: absolute workspace root path
            graph: shared KnowledgeGraph
            encoder: shared EncoderLayer
            llm: the LLM provider (IPP node or raw provider)
        """
        self.agent_id = agent_id
        self.root = Path(root) if root else \
            Path(__file__).resolve().parents[2] / "recursive_agents"
        self.ws_root = ws_root
        self.graph = graph
        self.encoder = encoder
        self.llm = llm
        self.tools: dict[str, BaseTool] = {}
        self.constructed: dict[str, Any] = {}   # agent_aX → engine
        self.chain: list[str] = []
        self._register_core()

    # ── registry ─────────────────────────────────────────────────────────
    def register(self, tool: BaseTool) -> None:
        self.tools[tool.tool_name] = tool

    def register_many(self, tools: list[BaseTool]) -> None:
        for t in tools:
            self.register(t)

    def get(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)

    def names(self) -> list[str]:
        return sorted(self.tools)

    def definitions(self) -> list[dict]:
        return [t.definition() for t in self.tools.values()]

    def execute(self, name: str, args: dict, ctx: ToolContext) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult.fail(f"Unknown tool: {name!r}")
        return tool._run(args or {}, ctx)

    def _register_core(self) -> None:
        self.register_many([
            AgentPlanTool(self), AgentGenerateTool(self),
            AgentCreateTool(self), AgentEvaluateTool(self),
            AgentTestTool(self), AgentImproveTool(self),
            AgentDeployTool(self), AgentStatusTool(self),
        ])

    # ── construction machinery (what the tools invoke) ───────────────────
    def plan(self, agent_id: str, level: Optional[int] = None) -> dict:
        name = _agent_name(agent_id)
        lvl = level or _level_of(name)
        return {"ok": True, "agent_id": name, "level": lvl,
                "steps": ["agent_generate", "agent_create",
                          "agent_evaluate", "agent_test",
                          "agent_improve", "agent_deploy"],
                "target_folders": {
                    "agent": str(self.root / name),
                    "engine": str(self.root / name / f"{name}_engine"),
                    "tools": str(self.root / name / f"{name}_tools")}}

    def generate(self, agent_id: str, level: int = 1,
                 generated_by: Optional[str] = None) -> dict:
        """REAL filesystem generation: render the templates and write the
        next agent's engine + tools folders."""
        name = _agent_name(agent_id)
        agent_dir = self.root / name
        engine_dir = agent_dir / f"{name}_engine"
        tools_dir = agent_dir / f"{name}_tools"
        engine_pkg = f"recursive_agents.{name}.{name}_engine"
        tools_pkg = f"recursive_agents.{name}.{name}_tools"
        by = generated_by or self.agent_id

        files = {
            "engine_IPP.json": engine_dir / "IPP.json",
            "engine_IPP_object.py": engine_dir / "IPP_object.py",
            "engine_IPP_executor.py": engine_dir / "IPP_executor.py",
            "tools_IPP.json": tools_dir / "IPP.json",
            "tools_IPP_object.py": tools_dir / "IPP_object.py",
            "tools_IPP_executor.py": tools_dir / "IPP_executor.py",
            "README_agent.md": agent_dir / "README.md",
            "README_engine.md": engine_dir / "README.md",
            "README_tools.md": tools_dir / "README.md",
            "system_prompt.md": agent_dir / "system_prompt.md",
        }
        for tpl, target in files.items():
            text = (self.TEMPLATES / tpl).read_text(encoding="utf-8")
            node_id = f"{name}_tools" if tpl.startswith("tools_") \
                else f"{name}_engine"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                _render(text, name=name, node_id=node_id,
                        engine_pkg=engine_pkg, tools_pkg=tools_pkg,
                        level=level, generated_by=by),
                encoding="utf-8")
        # validate the F-files AFTER writing (so the agent sees errors)
        json.loads((engine_dir / "IPP.json").read_text(encoding="utf-8"))
        json.loads((tools_dir / "IPP.json").read_text(encoding="utf-8"))
        for d, tag in ((agent_dir, "agent"), (engine_dir, "engine"),
                       (tools_dir, "tools")):
            (d / "__init__.py").write_text(
                f'"""\n{name} {tag} — generated by {by} (level {level}).\n"""\n',
                encoding="utf-8")
        return {"ok": True, "agent_id": name, "level": level,
                "folders": {"agent": str(agent_dir),
                            "engine": str(engine_dir),
                            "tools": str(tools_dir)},
                "generated_by": by}

    def construct(self, agent_id: str, level: int = 1) -> dict:
        """REAL construction: Γ ⊩ the generated F-files × 𝒢 ↝ engine +
        tools IPP nodes (using the GENERATED executor modules)."""
        from IPP.IPP_constructor import IPPConstructor
        from IPP.IPP_registry import GraphContext
        from recursive_agents.runtime.engine import RecursiveAgentEngine

        name = _agent_name(agent_id)
        agent_dir = self.root / name
        engine_dir = agent_dir / f"{name}_engine"
        tools_dir = agent_dir / f"{name}_tools"
        if not (engine_dir / "IPP.json").exists():
            return {"ok": False, "error": "not_generated",
                    "message": f"{name} not generated yet"}
        engine_pkg = f"recursive_agents.{name}.{name}_engine"
        tools_pkg = f"recursive_agents.{name}.{name}_tools"
        engine_exec = importlib.import_module(f"{engine_pkg}.IPP_executor")
        tools_exec = importlib.import_module(f"{tools_pkg}.IPP_executor")

        engine = RecursiveAgentEngine(
            graph=getattr(self, "graph", None),
            encoder=getattr(self, "encoder", None),
            llm=getattr(self, "llm", None),
            agent_id=name, level=level,
            toolkit=self,    # the agent's OWN toolkit (its tools)
        )
        ctx = GraphContext()
        ctx.bind("engine", engine)
        ctx.bind("toolkit", self)
        ctx.bind("agent_id", name)
        # the generated tools node needs the general ACL too
        from recursive_agents.runtime.engine import RECURSIVE_TOOL_NAMES
        ctx.bind("tool_names", list(RECURSIVE_TOOL_NAMES))
        gamma_e = IPPConstructor(
            ctx, executor_classes={ch: engine_exec.AgentExecutor
                                   for ch in ("ground", "chat",
                                              "chat_stream")})
        engine_node = gamma_e.construct_file(engine_dir / "IPP.json", ctx)
        gamma_e.recall_scope(engine_node)
        ctx.register_node(engine_node)
        gamma_t = IPPConstructor(
            ctx, executor_classes={ch: tools_exec.ToolExecutor
                                   for ch in self.tools})
        tools_node = gamma_t.construct_file(tools_dir / "IPP.json", ctx)
        gamma_t.recall_scope(tools_node)
        ctx.register_node(tools_node)
        engine.node = engine_node
        engine._tools_node = tools_node
        engine._ipp_context = ctx
        self.constructed[name] = engine
        return {"ok": True, "agent_id": name, "level": level,
                "engine_node": engine_node.node_id,
                "tools_node": tools_node.node_id}

    def evaluate(self, agent_id: str) -> dict:
        from IPP.IPP_verify import verify_node
        name = _agent_name(agent_id)
        engine = self.constructed.get(name)
        if engine is None:
            return {"ok": False, "error": "not_constructed",
                    "message": f"{name} not constructed"}
        ef = verify_node(engine.node)
        tf = verify_node(engine._tools_node)
        audits = (all(ex.audit_verify()
                      for ex in engine.node.executors.values())
                  and all(ex.audit_verify()
                          for ex in engine._tools_node.executors.values()))
        return {"ok": not ef and not tf,
                "engine_failures": ef, "tools_failures": tf,
                "audit_chains": audits,
                "engine_channels": engine.node.channels,
                "tools_channels": engine._tools_node.channels}

    def test(self, agent_id: str) -> dict:
        name = _agent_name(agent_id)
        if name not in self.constructed:
            self.construct(agent_id)
        engine = self.constructed[name]
        feedback = {"agent_id": name, "checks": {}, "issues": []}
        try:
            res = engine.node.invoke("ground", {"task": "Reply with OK only"})
            answer = str(res.payload.get("answer", "")) if isinstance(
                res.payload, dict) else str(res.payload)
            ok_ = "OK" in answer
            feedback["checks"]["chat_pipeline"] = ok_
            if not ok_:
                feedback["issues"].append("chat_pipeline: answer missing OK")
        except Exception as exc:  # noqa: BLE001
            feedback["checks"]["chat_pipeline"] = False
            feedback["issues"].append(f"chat_pipeline raised: {exc}")
        try:
            latency = int(engine.node.executors["chat"].policy.get(
                "max_latency_ms", 0))
            feedback["latency_ms"] = latency
            if latency < 600000:
                feedback["issues"].append(
                    f"chat latency policy {latency}ms < 600000ms")
                feedback["checks"]["latency"] = False
            else:
                feedback["checks"]["latency"] = True
        except Exception as exc:  # noqa: BLE001
            feedback["issues"].append(f"latency probe failed: {exc}")
        ev = self.evaluate(name)
        feedback["checks"]["invariants"] = ev["ok"]
        feedback["checks"]["audit_chains"] = ev["audit_chains"]
        if not ev["ok"]:
            feedback["issues"].append(
                f"invariants: {ev['engine_failures'] or []} / "
                f"{ev['tools_failures'] or []}")
        feedback["ok"] = not feedback["issues"]
        return feedback

    def improve(self, agent_id: str, iterations: int = 3) -> dict:
        name = _agent_name(agent_id)
        patches: list[str] = []
        rounds: list[dict] = []
        final: dict = {}
        for i in range(1, max(1, iterations) + 1):
            fb = self.test(agent_id)
            rounds.append({"round": i, "ok": fb["ok"],
                           "issues": fb["issues"]})
            if fb["ok"]:
                final = fb
                break
            patch = self._patch(name, fb)
            if patch is None:
                final = fb
                break
            patches.append(patch)
            self.constructed.pop(name, None)
            self.construct(agent_id)
        else:
            final = self.test(agent_id)
        report = {"ok": final.get("ok", False), "agent_id": name,
                  "iterations": len(rounds), "rounds": rounds,
                  "patches": patches, "final": final}
        self._write_feedback(name, report)
        return report

    def _patch(self, name: str, feedback: dict) -> Optional[str]:
        f = self.root / name / f"{name}_engine" / "IPP.json"
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
            return f"chat latency policy → 600000ms ({name}_engine/IPP.json)"
        return None

    def _write_feedback(self, name: str, report: dict) -> None:
        d = self.root / "feedback"
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"# {name} — improvement feedback ({stamp})",
                 f"ok: {report['ok']}", f"iterations: {report['iterations']}",
                 f"patches: {report['patches']}", "rounds:"]
        for r in report["rounds"]:
            lines.append(f"  round {r['round']}: ok={r['ok']} "
                         f"issues={r['issues']}")
        (d / f"{name}.txt").write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")

    def deploy(self, agent_id: str, level: Optional[int] = None) -> dict:
        name = _agent_name(agent_id)
        lvl = level or _level_of(name)
        if name not in self.constructed:
            self.generate(agent_id, lvl)
            self.construct(agent_id, lvl)
        if name not in self.chain:
            self.chain.append(name)
        return {"ok": True, "agent_id": name, "level": lvl,
                "chain": list(self.chain),
                "constructed": self.evaluate(name)["ok"],
                "message": f"{name} deployed; chain = {self.chain}"}

    def status(self) -> dict:
        return {"ok": True, "chain": list(self.chain),
                "constructed": sorted(self.constructed)}


# ══════════════════════════════════════════════════════════════════════
# the agent-construction tools (REAL — they invoke the toolkit)
# ══════════════════════════════════════════════════════════════════════
class AgentPlanTool(BaseTool):
    tool_name = "agent_plan"
    category = "constructor"
    description = "THINK: produce the deterministic construction plan for the next recursive agent."
    tool_schema = {"type": "object", "required": ["agent_id"],
                   "properties": {"agent_id": {"type": "string"},
                                  "level": {"type": "integer"}}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.plan(args.get("agent_id", ""), args.get("level"))
        return ToolResult.success(json.dumps(r, ensure_ascii=False, indent=1), **{k: v for k, v in r.items() if k != 'ok'})


class AgentGenerateTool(BaseTool):
    tool_name = "agent_generate"
    category = "constructor"
    description = "GENERATE: write the next recursive agent's engine + tools folders from the templates (REAL filesystem work)."
    tool_schema = {"type": "object", "required": ["agent_id"],
                   "properties": {"agent_id": {"type": "string"},
                                  "level": {"type": "integer"}}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.generate(args.get("agent_id", ""),
                             int(args.get("level") or 1))
        if r.get("ok"):
            return ToolResult.success(
f"generated {r['agent_id']} (by {r['generated_by']}): "
                f"{r['folders']['engine']}", **{k: v for k, v in r.items() if k != 'ok'})
        return ToolResult.fail(r.get("message", "generate failed"), **r)


class AgentCreateTool(BaseTool):
    tool_name = "agent_create"
    category = "constructor"
    description = "CREATE: construct the next agent's engine + tools IPP nodes through Γ (7-step protocol) + verify ALL 17 invariants."
    tool_schema = {"type": "object", "required": ["agent_id"],
                   "properties": {"agent_id": {"type": "string"},
                                  "level": {"type": "integer"}}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.construct(args.get("agent_id", ""),
                              int(args.get("level") or 1))
        if not r.get("ok"):
            return ToolResult.fail(r.get("message", "construct failed"), **r)
        ev = self.tk.evaluate(r["agent_id"])
        r.update({"verified": ev["ok"],
                  "engine_failures": ev["engine_failures"],
                  "tools_failures": ev["tools_failures"],
                  "audit_chains": ev["audit_chains"]})
        return ToolResult.success(
f"{r['agent_id']} constructed + "
            f"{'ALL 17 OK' if ev['ok'] else 'FAILED'}", **{k: v for k, v in r.items() if k != 'ok'})


class AgentEvaluateTool(BaseTool):
    tool_name = "agent_evaluate"
    category = "constructor"
    description = "EVALUATE: 17 invariants + audit chains + channel surface of a constructed agent."
    tool_schema = {"type": "object", "required": ["agent_id"],
                   "properties": {"agent_id": {"type": "string"}}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.evaluate(args.get("agent_id", ""))
        return ToolResult.success(
            f"{r.get('agent_id', args.get('agent_id'))}: "
            f"{'ALL 17 OK' if r['ok'] else r['engine_failures'] or r['tools_failures']}", **{k: v for k, v in r.items() if k != 'ok'})


class AgentTestTool(BaseTool):
    tool_name = "agent_test"
    category = "constructor"
    description = "TEST: run the ground→chat pipeline through the envelopes + latency probe + invariants → structured feedback."
    tool_schema = {"type": "object", "required": ["agent_id"],
                   "properties": {"agent_id": {"type": "string"}}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.test(args.get("agent_id", ""))
        return ToolResult.success(
f"{r['agent_id']} test: ok={r['ok']} issues={r['issues']}", **{k: v for k, v in r.items() if k != 'ok'})


class AgentImproveTool(BaseTool):
    tool_name = "agent_improve"
    category = "constructor"
    description = "IMPROVE: test → deterministic patch → reconstruct → retest until the agent passes (feedback logged)."
    tool_schema = {"type": "object", "required": ["agent_id"],
                   "properties": {"agent_id": {"type": "string"},
                                  "iterations": {"type": "integer"}}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.improve(args.get("agent_id", ""),
                            int(args.get("iterations") or 3))
        return ToolResult.success(
            f"{r['agent_id']}: {r['iterations']} rounds, "
            f"patches={r['patches']}, ok={r['ok']}", **{k: v for k, v in r.items() if k != 'ok'})


class AgentDeployTool(BaseTool):
    tool_name = "agent_deploy"
    category = "constructor"
    description = "DEPLOY: generate + construct + register the agent in the chain."
    tool_schema = {"type": "object", "required": ["agent_id"],
                   "properties": {"agent_id": {"type": "string"},
                                  "level": {"type": "integer"}}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.deploy(args.get("agent_id", ""), args.get("level"))
        return ToolResult.success(r.get("message", "deployed"), **{k: v for k, v in r.items() if k != 'ok'})


class AgentStatusTool(BaseTool):
    tool_name = "agent_status"
    category = "constructor"
    description = "Report the constructed recursive chain."
    tool_schema = {"type": "object", "properties": {}}

    def __init__(self, tk: AgentToolkit):
        self.tk = tk

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        r = self.tk.status()
        return ToolResult.success(f"chain = {r['chain']}", **{k: v for k, v in r.items() if k != 'ok'})


# ── helpers ─────────────────────────────────────────────────────────────────
def _agent_name(agent_id: str) -> str:
    a = str(agent_id).strip().lower().replace("agent_", "").replace(" ", "_")
    return f"agent_{a}"


def _level_of(name: str) -> int:
    m = re.search(r"\d+", name)
    return int(m.group(0)) if m else 1


def _render(text: str, name: str, node_id: str, engine_pkg: str,
            tools_pkg: str, level: int, generated_by: str) -> str:
    return (text
            .replace("{node_id}", node_id)
            .replace("{agent_id}", name)
            .replace("{engine_pkg}", engine_pkg)
            .replace("{tools_pkg}", tools_pkg)
            .replace("{log_dir}", AgentToolkit.LOG_DIR)
            .replace("__AGENT_ID__", name)
            .replace("__ENGINE_PKG__", engine_pkg)
            .replace("__TOOLS_PKG__", tools_pkg)
            .replace("__NODE_ID__", node_id)
            .replace("__LEVEL__", str(level))
            .replace("__GENERATED_BY__", generated_by))
