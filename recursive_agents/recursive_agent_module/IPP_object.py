"""
recursive_agent_module.IPP_object — Ω handlers for the recursive agent IPP node.

Five channels, each a handler factory that wraps the recursive agent
operations. The Flask server calls these through the IPP guardrail
envelope — it never imports agent internals directly.

Channels:
  chain             — scan disk for all recursive agents
  instruct          — Live LLM agent instruction
  instruct_offline  — deterministic quick construction
  verify            — run verification checks
  diff              — compare two agents
"""
from __future__ import annotations

import json, logging, re, time
from pathlib import Path
from typing import Any

logger = logging.getLogger("recursive_agent_module")

# ── module-level cache (same lifecycle as the node) ───────────────────────
_cache: dict[str, Any] = {}
_lock = None  # set by bind() — shared with the Flask server's threading lock


def bind(lock, graph=None, encoder=None, provider=None):
    """Bind shared resources from the Flask server."""
    global _lock
    _lock = lock
    if graph is not None and "graph" not in _cache:
        _cache["graph"] = graph
    if encoder is not None and "encoder" not in _cache:
        _cache["encoder"] = encoder
    if provider is not None and "provider" not in _cache:
        _cache["provider"] = provider


def _ws_root() -> Path:
    from general_tools.config import Config
    return Config.WORKSPACE_ROOT


def _agent_level(agent_id: str) -> int:
    m = re.search(r"agent_a(\d+)", agent_id)
    return int(m.group(1)) if m else 1


def _get_toolkit(agent_id: str):
    """Lazy-load an agent's toolkit (cached per agent_id)."""
    key = f"tk_{agent_id}"
    if key in _cache:
        return _cache[key]
    from recursive_agents.agent_a1.agent_a1_tools.tool_registry import AgentA1Toolkit
    tk = AgentA1Toolkit(
        agent_id=agent_id,
        ws_root=str(_ws_root()),
        graph=_cache.get("graph"),
        encoder=_cache.get("encoder"),
        llm=_cache.get("provider"),
    )
    tk.register_all()
    _cache[key] = tk
    return tk


# ═══════════════════════════════════════════════════════════════════════════
# chain — scan disk for all recursive agents
# ═══════════════════════════════════════════════════════════════════════════
def make_chain_handler(bindings: dict):
    def handler(payload: Any, context: dict) -> dict:
        agents = []
        root = _ws_root() / "recursive_agents"
        for d in sorted(root.iterdir()):
            if not d.is_dir() or not d.name.startswith("agent_"):
                continue
            if d.name in ("agent_a0_tools", "agent_agent_a2"):
                continue
            agent_id = d.name
            level = _agent_level(agent_id)
            tools_dir = d / f"{agent_id}_tools"
            tool_count = len(list(tools_dir.glob("*.py"))) if tools_dir.exists() else 0
            has_engine = (d / f"{agent_id}_engine" / "IPP.json").exists()
            has_tools = (d / f"{agent_id}_tools" / "IPP.json").exists()
            agents.append({
                "agent_id": agent_id, "level": level,
                "tools": tool_count,
                "status": "constructed" if (has_engine and has_tools) else "generated",
                "has_engine": has_engine, "has_tools": has_tools,
                "has_readme": (d / "README.md").exists(),
                "has_prompt": (d / "system_prompt.md").exists(),
            })
        return {"ok": True, "agents": agents, "count": len(agents)}
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# instruct — Live LLM agent instruction
# ═══════════════════════════════════════════════════════════════════════════
def make_instruct_handler(bindings: dict):
    def handler(payload: dict, context: dict) -> dict:
        agent_id = (payload.get("agent_id") or "").strip()
        task = (payload.get("task") or "").strip()
        if not agent_id or not task:
            return {"ok": False, "error": "agent_id and task required"}

        if _lock:
            _lock.acquire()
        try:
            import time as _time_check  # ensure time is in scope for Flask thread
            tk = _get_toolkit(agent_id)
            from recursive_agents.runtime.engine import RecursiveAgentEngine
            engine = RecursiveAgentEngine(
                graph=_cache.get("graph"),
                encoder=_cache.get("encoder"),
                llm=_cache.get("provider"),
                agent_id=agent_id,
                level=_agent_level(agent_id),
                toolkit=tk,
            )
            t0 = time.time()
            trace_entries: list[dict] = []
            answer = ""
            for event in engine.chat_stream(task):
                entry: dict = {"type": event.type}
                if event.tool:
                    entry["tool"] = event.tool
                    entry["args"] = event.args
                if event.content and event.type in ("text", "message"):
                    entry["content"] = str(event.content)[:500]
                    answer += (event.content or "")
                if event.type == "tool_result":
                    entry["content"] = str(event.content)[:300]
                if event.error:
                    entry["error"] = event.error
                trace_entries.append(entry)
            return {
                "ok": True, "agent_id": agent_id,
                "answer": answer[:2000],
                "trace": trace_entries[-30:],
                "chain": list(tk.chain),
                "constructed": sorted(tk.constructed),
                "tool_calls": sum(1 for e in trace_entries if e.get("type") == "tool_call"),
                "tools_used": sorted(set(e.get("tool", "") for e in trace_entries if e.get("tool"))),
                "elapsed": time.time() - t0,
            }
        except Exception as exc:
            import traceback
            logger.exception("instruct(%s) failed", agent_id)
            return {"ok": False, "error": str(exc),
                    "traceback": traceback.format_exc()[-800:]}
        finally:
            if _lock:
                _lock.release()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# instruct_offline — deterministic quick construction
# ═══════════════════════════════════════════════════════════════════════════
def make_instruct_offline_handler(bindings: dict):
    def handler(payload: dict, context: dict) -> dict:
        agent_id = (payload.get("agent_id") or "").strip()
        task = (payload.get("task") or "").strip()
        if not agent_id:
            return {"ok": False, "error": "agent_id required"}

        if _lock:
            _lock.acquire()
        try:
            tk = _get_toolkit(agent_id)
            ctx = type("ToolContext", (), {
                "workspace_root": str(_ws_root()),
                "agent": tk, "agent_name": agent_id, "session_id": "",
            })()

            target_m = re.search(r"agent_a(\d+)", task)
            target = f"agent_a{target_m.group(1)}" if target_m else "agent_a2"
            target_level = int(target_m.group(1)) if target_m else 2
            target_short = target.replace("agent_", "")

            steps = []
            for step_name, args in [
                ("plan", {"agent_id": target_short}),
                ("generate", {"agent_id": target_short, "level": target_level}),
                ("create", {"agent_id": target_short, "level": target_level}),
                ("evaluate", {"agent_id": target_short}),
                ("test", {"agent_id": target_short}),
                ("deploy", {"agent_id": target_short, "level": target_level}),
            ]:
                r = tk.execute(f"agent_{step_name}", args, ctx)
                steps.append({"step": step_name, "ok": r.ok,
                             "content": (r.content or "")[:200]})
            return {
                "ok": True, "agent_id": agent_id, "steps": steps,
                "chain": list(tk.chain),
                "constructed": sorted(tk.constructed),
            }
        except Exception as exc:
            import traceback
            logger.exception("instruct_offline(%s) failed", agent_id)
            return {"ok": False, "error": str(exc),
                    "traceback": traceback.format_exc()[-800:]}
        finally:
            if _lock:
                _lock.release()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# verify — run a verification check
# ═══════════════════════════════════════════════════════════════════════════
def make_verify_handler(bindings: dict):
    def handler(payload: dict, context: dict) -> dict:
        agent_id = (payload.get("agent_id") or "").strip()
        check = (payload.get("check") or "all").strip()
        if not agent_id:
            return {"ok": False, "error": "agent_id required"}

        if _lock:
            _lock.acquire()
        try:
            tk = _get_toolkit(agent_id)
            ctx = type("ToolContext", (), {
                "workspace_root": str(_ws_root()),
                "agent": tk, "agent_name": agent_id, "session_id": "",
            })()
            lookup = agent_id.replace("agent_", "")
            r = tk.execute(check, {"agent_id": lookup}, ctx)
            return {
                "ok": r.ok, "content": (r.content or "")[:500],
                "metadata": r.metadata if hasattr(r, "metadata") else {},
                "error": r.error,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            if _lock:
                _lock.release()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# diff — compare two agents
# ═══════════════════════════════════════════════════════════════════════════
def make_diff_handler(bindings: dict):
    def handler(payload: dict, context: dict) -> dict:
        a1 = (payload.get("agent1") or "").strip()
        a2 = (payload.get("agent2") or "").strip()
        if not a1 or not a2:
            return {"ok": False, "error": "agent1 and agent2 required"}

        root = _ws_root() / "recursive_agents"
        identical = []; name_only = []; different = []

        for d1 in (root / a1).rglob("*.py"):
            if "__pycache__" in str(d1):
                continue
            rel = d1.relative_to(root / a1)
            d2 = root / a2 / rel
            if not d2.exists():
                continue
            t1 = d1.read_text(encoding="utf-8", errors="replace")
            t2 = d2.read_text(encoding="utf-8", errors="replace")
            if t1 == t2:
                identical.append({"file": str(rel), "detail": "byte-identical"})
            else:
                n1 = re.sub(r'\b' + re.escape(a1) + r'\b', 'X', t1)
                n2 = re.sub(r'\b' + re.escape(a2) + r'\b', 'X', t2)
                if n1 == n2:
                    name_only.append({"file": str(rel), "detail": "name substitution only"})
                else:
                    different.append({"file": str(rel),
                                     "detail": f"{len(t1.splitlines())}L vs {len(t2.splitlines())}L"})

        return {
            "ok": True, "agent1": a1, "agent2": a2,
            "identical": identical, "name_only": name_only, "different": different,
            "summary": f"{len(identical)} identical, {len(name_only)} name-only, {len(different)} different",
        }
    return handler
