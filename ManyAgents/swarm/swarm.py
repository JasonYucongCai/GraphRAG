"""
swarm.swarm — the SwarmManager: runs many agents together.

The manager owns the 20 AgentRuntimes, the shared swarm bus and the
reference to the social_activity IPP node. All goal/task creation and
all result reporting go through the social node's guardrail envelope;
agent turns go through each agent's own engine node (AgentRuntime).

External-topology enforcement (strict IPP): the portal's ``swarm``
channel resolves its downstream targets at construction time against 𝒢;
``attach_topology`` captures that resolved set, and ``start`` only
dispatches to agents whose engine node is a resolved downstream target
(τ*_k conformance — no out-of-topology dispatch).
"""
from __future__ import annotations

import threading
from typing import Optional

from ManyAgents.swarm.bus import SwarmBus
from ManyAgents.swarm.responder import SocialResponder
from ManyAgents.swarm.runtime import AgentRuntime


class SwarmManager:
    """Concurrent multi-agent execution + goal/task orchestration."""

    def __init__(self, runtimes: list[AgentRuntime], social_node,
                 bus: Optional[SwarmBus] = None,
                 max_concurrent: int = 4, settings=None):
        self.runtimes: dict[str, AgentRuntime] = {
            r.agent_id: r for r in runtimes}
        self.social_node = social_node          # social_activity IPP node
        self.bus = bus or SwarmBus()
        self.settings = settings
        self._semaphore = threading.Semaphore(max_concurrent)
        for r in runtimes:
            r.concurrency = self._semaphore
        self._topology: set[tuple[str, str]] = set()   # resolved τ*_k targets
        self._lock = threading.RLock()
        # the conversation loop (agents reply to inbox messages)
        self.responder: Optional[SocialResponder] = None
        if settings is not None:
            self.responder = SocialResponder(self, settings,
                                             social_node=social_node)

    # ── settings ─────────────────────────────────────────────────────────
    def apply_settings(self) -> None:
        """Apply platform settings: concurrency budget + LLM call mode."""
        if self.settings is None:
            return
        max_conc = int(self.settings.get("max_concurrent", 4) or 4)
        with self._lock:
            if max_conc != getattr(self, "_max_concurrent", None):
                self._max_concurrent = max_conc
                self._semaphore = threading.Semaphore(max_conc)
                for r in self.runtimes.values():
                    r.concurrency = self._semaphore

    def start_responder(self) -> None:
        if self.responder is not None:
            self.responder.start()

    def stop_responder(self) -> None:
        if self.responder is not None:
            self.responder.stop()

    # ── topology (portal swarm channel) ──────────────────────────────────
    def attach_topology(self, downstream: list) -> None:
        """Capture the portal swarm channel's constructor-resolved targets."""
        with self._lock:
            self._topology = {(node_id, ch) for node_id, ch in downstream}

    def agent_addresses(self) -> dict[str, dict]:
        """agent_id → {engine_node, tools_node, status, ...} (addressing)."""
        out = {}
        for agent_id, rt in self.runtimes.items():
            out[agent_id] = {
                "engine_node": rt.engine.node.node_id if rt.engine.node else "",
                "tools_node": (rt.engine._tools_node.node_id
                               if getattr(rt.engine, "_tools_node", None)
                               else ""),
                "status": rt.status,
                "pending": rt.pending,
                "runs_completed": rt.runs_completed,
                "last_activity": rt.last_activity,
                "in_topology": (rt.engine.node.node_id, "chat_stream")
                               in self._topology,
            }
        return out

    # ── orchestration ────────────────────────────────────────────────────
    def start(self, goal_title: str, instructions: str,
              agent_ids: Optional[list[str]] = None,
              goal_id: Optional[str] = None) -> dict:
        """Create (or continue) the goal + one task per agent, then run them.

        Everything social goes through the social_activity node; agents
        are only started when their engine node is a resolved downstream
        target of the portal's swarm channel (strict τ* conformance).

        ``goal_id`` reuses an EXISTING goal folder (continue) instead of
        creating a new one — tasks are appended to it.
        """
        if not goal_title or not instructions:
            from IPP_Social.errors import SocialError
            raise SocialError("start requires goal + instructions",
                              code="bad_request")
        selected = [a for a in (agent_ids or list(self.runtimes))
                    if a in self.runtimes]
        if not selected:
            raise ValueError(f"no known agents in {agent_ids!r}")

        # 1) the goal folder in the social database (via IPP) — reuse or create
        if goal_id:
            existing = self.social_node.invoke(
                "tasks", {"op": "get_goal", "goal_id": goal_id}).payload
            if not existing.get("ok"):
                raise ValueError(f"unknown goal {goal_id}: "
                                 f"{existing.get('error')}")
            goal = existing["goal"]
            goal_id = goal["goal_id"]
        else:
            goal = self.social_node.invoke(
                "tasks", {"op": "create_goal", "title": goal_title,
                          "description": instructions}).payload
            if not goal.get("ok"):
                raise ValueError(f"social goal failed: {goal.get('error')}")
            goal_id = goal["goal"]["goal_id"]

        # 2) one task per agent (shared goal, per-agent assignment)
        started: list[str] = []
        for agent_id in selected:
            rt = self.runtimes[agent_id]
            # ── stuck-task recovery ──────────────────────────────────────
            # If a previous task is still 'processing' but the worker is
            # idle (the worker died / the task was never picked up), clear
            # the stale task so the fresh one below is the only pending one.
            try:
                stale = self.social_node.invoke(
                    "tasks", {"op": "list_tasks", "goal_id": goal_id,
                              "status": "processing"}).payload
                for t in (stale.get("tasks") or []):
                    if t.get("assignee_agent_id") == agent_id and \
                            not rt.pending and not rt.alive:
                        self.social_node.invoke(
                            "tasks", {"op": "update_task",
                                      "goal_id": goal_id,
                                      "task_id": t.get("task_id"),
                                      "author_agent_id": "portal",
                                      "status": "failed",
                                      "note": "stale task — worker was "
                                              "restarted"})
            except Exception:  # noqa: BLE001 — recovery is best-effort
                pass
            node = rt.engine.node
            if node is None or (node.node_id, "chat_stream") \
                    not in self._topology:
                self.bus.emit("swarm_skipped", agent_id,
                              {"reason": "engine node outside resolved "
                                         "portal topology"})
                continue
            task = self.social_node.invoke(
                "tasks", {"op": "create_task", "goal_id": goal_id,
                          "title": f"{agent_id}: {goal_title}",
                          "description": instructions,
                          "assignee_agent_id": agent_id,
                          "author_agent_id": "portal",
                          "status": "processing"}).payload
            if not task.get("ok"):
                self.bus.emit("agent_error", agent_id,
                              {"phase": "task_create",
                               "error": task.get("error")})
                continue
            rt.enqueue({"task_id": task["task"]["task_id"],
                        "goal_id": goal_id, "text": instructions})
            rt.start()
            started.append(agent_id)
        self.bus.emit("swarm_started", "portal",
                      {"goal_id": goal_id, "goal_title": goal_title,
                       "agents": started})
        # ── auto-start the conversation loop when the team starts ──
        self.start_responder()
        return {"ok": True, "goal_id": goal_id, "agents": started,
                "status": self.status()}

    def instruct(self, agent_id: str, instruction: str,
                 goal_id: Optional[str] = None) -> dict:
        """Give one individual agent a direct instruction (portal command).

        The instruction becomes a task in the given goal (or a dedicated
        "portal-instructions" goal) and the agent processes it.
        """
        if agent_id not in self.runtimes:
            from IPP_Social.errors import UnknownAgent
            raise UnknownAgent(f"unknown agent {agent_id!r}", agent_id=agent_id)
        if not instruction:
            from IPP_Social.errors import SocialError
            raise SocialError("instruct requires instruction text",
                              code="bad_request")
        if not goal_id:
            goal = self.social_node.invoke(
                "tasks", {"op": "create_goal", "title": "portal-instructions",
                          "description": "direct instructions from the "
                                         "portal user"}).payload
            goal_id = goal["goal"]["goal_id"]
        task = self.social_node.invoke(
            "tasks", {"op": "create_task", "goal_id": goal_id,
                      "title": f"{agent_id}: instruction",
                      "description": instruction,
                      "assignee_agent_id": agent_id,
                      "author_agent_id": "portal",
                      "status": "processing"}).payload
        rt = self.runtimes[agent_id]
        rt.enqueue({"task_id": task["task"]["task_id"],
                    "goal_id": goal_id, "text": instruction})
        rt.start()
        # also post the instruction to the chat board so it shows as
        # 👤 USER → Alice: <instruction> — visible to the whole team
        try:
            self.social_node.invoke("chat_board", {
                "op": "post", "author_agent_id": "user",
                "text": instruction, "to_agent_id": agent_id})
        except Exception:
            pass  # board post is best-effort; never block the instruction
        self.bus.emit("agent_instructed", agent_id,
                      {"goal_id": goal_id, "text": instruction[:200]})
        return {"ok": True, "goal_id": goal_id,
                "task_id": task["task"]["task_id"], "agent_id": agent_id}

    def stop(self) -> dict:
        """Stop all runtimes (pending tasks are dropped) + stop responder."""
        self.stop_responder()
        for rt in self.runtimes.values():
            rt.stop(cancel_pending=True)
        self.bus.emit("swarm_stopped", "portal", {})
        return {"ok": True, "status": self.status()}

    def status(self) -> dict:
        """Per-agent status + aggregate counters."""
        agents = []
        running = done = error = idle = 0
        for agent_id in sorted(self.runtimes):
            rt = self.runtimes[agent_id]
            st = rt.status
            if st == "running":
                running += 1
            elif st == "done":
                done += 1
            elif st == "error":
                error += 1
            else:
                idle += 1
            agents.append({"agent_id": agent_id, "status": st,
                           "pending": rt.pending,
                           "runs_completed": rt.runs_completed,
                           "last_activity": rt.last_activity,
                           "current_task": (rt.current_task or {}).get(
                               "text", "")[:120]})
        return {"running": running, "done": done, "error": error,
                "idle": idle, "total": len(self.runtimes),
                "agents": agents}
