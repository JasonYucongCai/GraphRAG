"""
swarm.runtime — one AgentRuntime per ManyAgents agent.

Each runtime owns:

  • the agent's engine (with its personality system prompt) and its IPP
    nodes (engine node + tools node) constructed in the shared 𝒢
  • a task queue — the swarm enqueues goal tasks assigned to this agent
  • a worker thread that executes tasks STRICTLY through the agent's
    engine IPP node guardrail envelope (``node.invoke("chat_stream", …)``),
    pushing every observable step live onto the swarm bus
  • social completion: after each task the runtime reports the result
    back through the social_activity node (task status update + a
    chat-board post) — the collaboration trail is fully social.

Runtime status is queryable by the portal (idle | running | done |
error), with the current task and a short activity line.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

from IPP_Social.swarm.bus import SwarmBus


class AgentRuntime:
    """One concurrent agent worker (thread + task queue + IPP execution)."""

    def __init__(self, agent_id: str, engine, bus: SwarmBus,
                 social_node, concurrency: Optional[threading.Semaphore] = None,
                 max_answer_chars: int = 400, settings=None):
        self.agent_id = agent_id
        self.engine = engine
        self.bus = bus
        self.social_node = social_node          # the social_activity IPP node
        self.concurrency = concurrency          # shared swarm limiter
        self.max_answer_chars = max_answer_chars
        self.settings = settings or {}          # SettingsStore (shared)

        self._queue: "queue.Queue[Optional[dict]]" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_loop, name=f"swarm-{agent_id}", daemon=True)
        self._stop = False

        # observable status (read by portal.discover)
        self.status: str = "idle"               # idle|running|done|error
        self.current_task: Optional[dict] = None
        self.last_activity: str = ""
        self.runs_completed: int = 0
        self._status_lock = threading.RLock()

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        """Start (or restart) the worker.

        A worker whose thread already ran to completion (e.g. after
        ``stop()``) cannot be ``start()``-ed again — a fresh thread is
        created so a stopped runtime can be reused for later tasks.
        """
        if self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(
            target=self._run_loop, name=f"swarm-{self.agent_id}", daemon=True)
        self._thread.start()

    def stop(self, cancel_pending: bool = True) -> None:
        """Stop the worker; queued tasks are dropped when cancel_pending."""
        self._stop = True
        if cancel_pending:
            try:
                while True:
                    self._queue.get_nowait()
            except queue.Empty:
                pass
        self._queue.put(None)                   # wake the worker

    def join(self, timeout: Optional[float] = None) -> None:
        self._thread.join(timeout=timeout)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    # ── task intake ──────────────────────────────────────────────────────
    def enqueue(self, task: dict) -> None:
        """Queue one task: {task_id, goal_id, text, node_id?}."""
        self._queue.put(task)

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    # ── worker ───────────────────────────────────────────────────────────
    def _set_status(self, status: str, activity: str = "") -> None:
        with self._status_lock:
            self.status = status
            if activity:
                self.last_activity = activity

    def _run_loop(self) -> None:
        while not self._stop:
            task = self._queue.get()
            if task is None:
                break
            self._process(task)
        self._set_status("idle", "worker stopped")

    def _process(self, task: dict) -> None:
        self.current_task = task
        self._set_status("running", f"task: {task.get('text', '')[:80]}")
        self.bus.emit("agent_started", self.agent_id,
                      {"task_id": task.get("task_id"),
                       "goal_id": task.get("goal_id"),
                       "text": task.get("text", "")})
        try:
            if self.concurrency is not None:
                self.concurrency.acquire()
            try:
                # the LLM call mode follows the platform settings:
                # many agents default to NON-streaming (concurrent-friendly)
                self.engine.llm_stream = bool(
                    getattr(self.settings, "get", lambda k, d: d)(
                        "llm_streaming", False))
                # STRICT IPP: the whole turn runs through the agent's engine
                # node guardrail envelope; the live handler pushes each
                # observable event onto the swarm bus via context["on_event"].
                guarded = self.engine.node.invoke(
                    "chat_stream",
                    {"task": task.get("text", ""),
                     "node_id": task.get("node_id")},
                    context={"on_event": self._on_event})
            finally:
                if self.concurrency is not None:
                    self.concurrency.release()
            out = guarded.payload or {}
            answer = str(out.get("answer", ""))
            tokens = int(out.get("tokens", 0) or 0)
            self.runs_completed += 1
            self._set_status("done", f"answer: {answer[:80]}")
            self._complete_socially(task, answer, tokens, error=None)
        except Exception as exc:  # noqa: BLE001 — surface, never kill
            self._set_status("error", str(exc)[:120])
            self.bus.emit("agent_error", self.agent_id,
                          {"task_id": task.get("task_id"),
                           "error": str(exc)})
            self._complete_socially(task, "", 0, error=str(exc))
        finally:
            self.current_task = None

    def _on_event(self, agent_id: str, entry: dict) -> None:
        """Live push of one observable step (from the IPP chat_stream handler)."""
        self.bus.emit("agent_event", agent_id, {
            "event": entry,
            "task_id": (self.current_task or {}).get("task_id"),
        })

    # ── social completion (through the social_activity node) ─────────────
    def _complete_socially(self, task: dict, answer: str, tokens: int,
                           error: Optional[str]) -> None:
        goal_id = task.get("goal_id")
        task_id = task.get("task_id")
        # reply tasks (the conversation loop) are their own answer — the
        # agent already posted the reply; no extra board broadcast.
        if task.get("reply"):
            return
        try:
            if goal_id and task_id:
                note = (f"answer({tokens} tok): {answer[:self.max_answer_chars]}"
                        if answer else f"error: {error}")
                self.social_node.invoke(
                    "tasks", {"op": "update_task", "goal_id": goal_id,
                              "task_id": task_id,
                              "author_agent_id": self.agent_id,
                              "status": "completed" if not error else "failed",
                              "note": note})
            # broadcast the outcome on the global chat board,
            # addressed to the agents (inter-agent chat)
            snippet = answer[:self.max_answer_chars] if answer else (error or "")
            if snippet:
                self.social_node.invoke(
                    "chat_board", {"op": "post",
                                   "author_agent_id": self.agent_id,
                                   "text": f"[{task.get('goal_id', 'swarm')}] "
                                           f"{snippet}",
                                   "tags": ["swarm", "done"],
                                   "to_agent_id": "agents"})
        except Exception as exc:  # noqa: BLE001 — social write failures are
            self.bus.emit("agent_error", self.agent_id,  # non-fatal
                          {"phase": "social_completion", "error": str(exc)})
