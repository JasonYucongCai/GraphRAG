"""
IPP.IPP_multiprocess_client — cross-process HTTP client.

Used by child processes (Multi Agent, Recursive Agent) to forward
shared-resource tool calls to the Control Center process.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

from IPP.IPP_multiprocess_config import (
    HOST, CONTROL_PORT, INTERNAL_INVOKE, REQUEST_TIMEOUT,
)

logger = logging.getLogger("IPP.multiprocess_client")


class RemoteInvokeClient:
    """HTTP client that calls the Control Center's internal invoke API.

    One instance per process — the host/port are fixed by configuration.
    """

    def __init__(self, host: str = HOST, port: int = CONTROL_PORT):
        self._base = f"http://{host}:{port}"
        self._endpoint = f"{self._base}{INTERNAL_INVOKE}"

    # ── primary surface ───────────────────────────────────────────────────
    def invoke_tool(self, tool: str, args: dict | None = None,
                    agent_id: str = "", session_id: str = "",
                    workspace_root: str = "") -> dict:
        """POST /api/internal/invoke → {ok, content, error, metadata}.

        Mirrors the shared tools_node's invoke channel exactly so callers
        don't need to know whether the tool runs locally or remotely.
        """
        payload: dict[str, Any] = {
            "tool": tool,
            "args": args or {},
            "agent_id": agent_id,
            "session_id": session_id,
            "workspace_root": workspace_root,
        }
        return self._post(self._endpoint, payload)

    # ── helpers ───────────────────────────────────────────────────────────
    def _post(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            logger.error("remote invoke failed: %s → %s", url, exc)
            return {"ok": False, "error": "remote_unreachable",
                    "content": f"[ERROR] Control Center unreachable: {exc}",
                    "metadata": {}}
        except Exception as exc:
            logger.error("remote invoke error: %s", exc)
            return {"ok": False, "error": "remote_error",
                    "content": f"[ERROR] {exc}", "metadata": {}}

    def health(self) -> bool:
        """True if the Control Center is reachable."""
        try:
            req = urllib.request.Request(
                f"{self._base}/api/health",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok"))
        except Exception:
            return False

    @property
    def base_url(self) -> str:
        return self._base
