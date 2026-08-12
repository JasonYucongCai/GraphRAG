"""
IPP.IPP_multiprocess_config — configuration for the three-process architecture.

Ports and internal-API endpoints shared by the orchestrator, bridge, and
cross-process client.  Every path lives in this one file so there is never
a port-number mismatch.
"""
from __future__ import annotations

# ── ports ──────────────────────────────────────────────────────────────────
CONTROL_PORT = 8000
MULTIAGENT_PORT = 8001
RECURSIVE_PORT = 8002

HOST = "127.0.0.3"

# ── internal API (Control Center ↔ other processes) ───────────────────────
# The Control Center exposes these so Multi Agent and Recursive Agent
# processes can dispatch shared-resource calls (graph, encoder, database,
# codex tools) back to the process that owns them.
INTERNAL_INVOKE = "/api/internal/invoke"
INTERNAL_GRAPH = "/api/internal/graph"
INTERNAL_ENCODER = "/api/internal/encoder"
INTERNAL_DATABASE = "/api/internal/database"

# ── proxy routes on Control Center that forward to child processes ────────
# The Control Center serves the main SPA and transparently proxies these
# path prefixes to the Multi Agent and Recursive Agent processes so the
# frontend never needs to know about separate ports.
MULTIAGENT_PROXY_PREFIXES = ("/api/multiagent/", "/api/social/", "/api/swarm/")
RECURSIVE_PROXY_PREFIXES = ("/api/recursive/",)

# ── timeouts ───────────────────────────────────────────────────────────────
STARTUP_TIMEOUT = 30.0     # seconds to wait for a child process to become ready
HEALTH_POLL_INTERVAL = 0.5 # seconds between readiness checks
REQUEST_TIMEOUT = 120.0    # seconds for cross-process HTTP calls
SHUTDOWN_TIMEOUT = 10.0    # seconds to wait for graceful shutdown

# ── tool route splitting ───────────────────────────────────────────────────
# In a child process, only these node_key targets execute LOCALLY.
# Everything else is forwarded to the Control Center via HTTP.
# (The Control Center always runs everything locally.)
LOCAL_NODE_KEYS: dict[str, set[str]] = {
    "multiagent": {"social_activity"},
    "recursive": set(),
}
