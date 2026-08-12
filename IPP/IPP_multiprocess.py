"""
IPP.IPP_multiprocess — the three-process orchestrator.

Spawns the Control Center (port 8000), Multi Agent portal (port 8001), and
Recursive Agent portal (port 8002) as independent OS-level processes and
monitors their health.  A single Ctrl‑C brings down all three gracefully.

Usage:
    python -m IPP.IPP_multiprocess [--graph DIR]

The Control Center owns the shared KnowledgeGraph, EncoderLayer, tools
node, database node, and LLM node.  Multi Agent and Recursive Agent
processes forward non-local tool calls back to the Control Center via
the internal HTTP API (IPP_multiprocess_bridge).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from IPP.IPP_multiprocess_config import (
    CONTROL_PORT, MULTIAGENT_PORT, RECURSIVE_PORT, HOST,
    STARTUP_TIMEOUT, HEALTH_POLL_INTERVAL, SHUTDOWN_TIMEOUT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [IPP.orchestrator] %(levelname)s %(message)s",
)
logger = logging.getLogger("IPP.multiprocess")

_WS = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = str(_WS / "ui" / "server.py")


# ══════════════════════════════════════════════════════════════════════════
# process management
# ══════════════════════════════════════════════════════════════════════════

def _python() -> str:
    return sys.executable


def _start_process(name: str, port: int, mode: str, *,
                   remote_backend: str = "",
                   graph_dir: str = "",
                   orchestrated: bool = False) -> subprocess.Popen:
    """Launch one portal process."""
    cmd = [
        _python(), SERVER_SCRIPT,
        "--port", str(port),
        "--mode", mode,
    ]
    if orchestrated:
        cmd.append("--orchestrated")
    if remote_backend:
        cmd += ["--remote-backend", remote_backend]
    if graph_dir:
        cmd += ["--graph", graph_dir]

    logger.info("starting %s on port %d (mode=%s)", name, port, mode)
    proc = subprocess.Popen(
        cmd,
        stdout=sys.stdout, stderr=sys.stderr,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        if os.name == "nt" else 0,
    )
    return proc


def _wait_ready(port: int, timeout: float = STARTUP_TIMEOUT) -> bool:
    """Poll /api/health until the process responds or timeout."""
    import urllib.request, json as _json
    deadline = time.time() + timeout
    url = f"http://{HOST}:{port}/api/health"
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                url, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as r:
                data = _json.loads(r.read().decode("utf-8"))
                if data.get("ok"):
                    return True
        except Exception:
            pass
        time.sleep(HEALTH_POLL_INTERVAL)
    return False


def _stop_process(proc: subprocess.Popen, name: str) -> None:
    """Graceful terminate, then kill."""
    if proc is None or proc.poll() is not None:
        return
    logger.info("stopping %s (pid=%d)…", name, proc.pid)
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=SHUTDOWN_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning("%s did not stop — killing", name)
            proc.kill()
            proc.wait(timeout=3)
    except Exception as exc:
        logger.warning("error stopping %s: %s", name, exc)
    logger.info("%s stopped", name)


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Graph Knowledge Network — three-process launcher")
    parser.add_argument(
        "--graph", dest="graph_dir", default=None,
        help="Custom graph_data/ folder for the Control Center")
    args = parser.parse_args()

    control_url = f"http://{HOST}:{CONTROL_PORT}"
    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        # ── 1. Control Center (shared backend) ─────────────────────────
        cc = _start_process(
            "Control Center", CONTROL_PORT, "control",
            graph_dir=args.graph_dir or "",
            orchestrated=True)
        processes.append(("Control Center", cc))

        if not _wait_ready(CONTROL_PORT):
            logger.error("Control Center did not become ready")
            return 1
        logger.info("Control Center ready at %s", control_url)

        # ── 2. Multi Agent portal ──────────────────────────────────────
        ma = _start_process(
            "Multi Agent", MULTIAGENT_PORT, "multiagent",
            remote_backend=control_url)
        processes.append(("Multi Agent", ma))

        if not _wait_ready(MULTIAGENT_PORT):
            logger.error("Multi Agent portal did not become ready")
            return 1
        logger.info("Multi Agent portal ready at http://%s:%d",
                    HOST, MULTIAGENT_PORT)

        # ── 3. Recursive Agent portal ──────────────────────────────────
        ra = _start_process(
            "Recursive Agent", RECURSIVE_PORT, "recursive",
            remote_backend=control_url)
        processes.append(("Recursive Agent", ra))

        if not _wait_ready(RECURSIVE_PORT):
            logger.error("Recursive Agent portal did not become ready")
            return 1
        logger.info("Recursive Agent portal ready at http://%s:%d",
                    HOST, RECURSIVE_PORT)

        # ── ready ──────────────────────────────────────────────────────
        print(
            "\n╔══════════════════════════════════════════════════════════╗\n"
            "║  Graph Knowledge Network — three-process platform          ║\n"
            "╠══════════════════════════════════════════════════════════╣\n"
            "║                                                        ║\n"
            f"║  Control Center   →  {control_url}                  ║\n"
            f"║  Multi Agent      →  http://{HOST}:{MULTIAGENT_PORT}                  ║\n"
            f"║  Recursive Agent  →  http://{HOST}:{RECURSIVE_PORT}                  ║\n"
            "║                                                        ║\n"
            "║  Press Ctrl+C to stop all three processes.              ║\n"
            "╚══════════════════════════════════════════════════════════╝\n"
        )

        # Wait for any process to exit (or Ctrl+C)
        while all(p.poll() is None for _, p in processes):
            time.sleep(1)

        # If we get here, at least one process exited unexpectedly
        for name, proc in processes:
            rc = proc.poll()
            if rc is not None:
                logger.error("%s exited unexpectedly (rc=%d)", name, rc)

        return 1

    except KeyboardInterrupt:
        logger.info("shutting down…")
    finally:
        for name, proc in reversed(processes):
            _stop_process(proc, name)
        logger.info("all processes stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
