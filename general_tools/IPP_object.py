"""
tools.IPP_object — the IPP Objects (Ω_k) of the tools node.

26 channels: invoke (the router), list / describe (the F-file catalog),
graph / encoder / build / check (op-dispatch over tools.impl), and the 19
codex channels (each = one codex_tools function wrapped as a handler —
per-tool guardrails and per-tool audit logs).

Handlers resolve the bound graph / encoder / agent registry / catalog
LIVE from ``tools.construct`` on every call, so rebinds (server startup,
platform assembly, graph rebuild) are honored without re-construction.

Domain errors are translated at this boundary into structured
``{"ok": false, "error": code, "message": ...}`` payloads — the Executor's
guardrail envelope (ι_pre → π → Ω → ι_post → ρ → τ*) wraps every call.
"""
from __future__ import annotations

from typing import Any


def _run(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — structured errors
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


# ════════════════════════════════════════════════════════════════════════
# invoke — the router (R*_k): tool name → the target channel's envelope
# ════════════════════════════════════════════════════════════════════════
def make_invoke_handler(bindings: dict):
    from general_tools.construct import impl_execute_tool

    def handler(payload: dict, context: dict) -> dict:
        return _run(lambda: impl_execute_tool(payload))

    return handler


# ════════════════════════════════════════════════════════════════════════
# list / describe — the definitions from the F-file catalog
# ════════════════════════════════════════════════════════════════════════
def make_list_handler(bindings: dict):
    from general_tools.impl import impl_list_tools

    def handler(payload: dict, context: dict) -> dict:
        return _run(lambda: impl_list_tools(payload))

    return handler


def make_describe_handler(bindings: dict):
    from general_tools.impl import impl_describe_tool

    def handler(payload: dict, context: dict) -> dict:
        return _run(lambda: impl_describe_tool(payload))

    return handler


# ════════════════════════════════════════════════════════════════════════
# graph / encoder / build / check — op-dispatch over tools.impl
# ════════════════════════════════════════════════════════════════════════
def make_graph_handler(bindings: dict):
    from general_tools.impl import impl_graph_op

    def handler(payload: dict, context: dict) -> dict:
        return _run(lambda: impl_graph_op(payload))

    return handler


def make_encoder_handler(bindings: dict):
    from general_tools.impl import impl_encoder_op

    def handler(payload: dict, context: dict) -> dict:
        return _run(lambda: impl_encoder_op(payload))

    return handler


def make_build_handler(bindings: dict):
    from general_tools.impl import impl_build_op

    def handler(payload: dict, context: dict) -> dict:
        return _run(lambda: impl_build_op(payload))

    return handler


def make_check_handler(bindings: dict):
    from general_tools.impl import impl_check_op

    def handler(payload: dict, context: dict) -> dict:
        return _run(lambda: impl_check_op(payload))

    return handler


# ════════════════════════════════════════════════════════════════════════
# the 19 codex channels — each wraps one codex_tools function
# ════════════════════════════════════════════════════════════════════════

def _codex_handler_for(fn):
    """Wrap a codex_tools function as an Ω handler (JSON-safe payload)."""

    def handler(payload: dict, context: dict) -> dict:
        try:
            out = fn(**payload) if isinstance(payload, dict) else fn(payload)
            return {"ok": True, "content": str(out), "error": None,
                    "metadata": {}}
        except TypeError as exc:  # noqa: BLE001
            return {"ok": False, "error": "bad_arguments",
                    "content": f"[ERROR] bad arguments: {exc}",
                    "metadata": {}}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "failed",
                    "content": f"[ERROR] {exc}", "metadata": {}}

    return handler


def make_shell_command_handler(bindings: dict):
    from general_tools.codex_tools import tool_shell_command
    return _codex_handler_for(tool_shell_command)


def make_read_file_handler(bindings: dict):
    from general_tools.codex_tools import tool_read_file
    return _codex_handler_for(tool_read_file)


def make_write_file_handler(bindings: dict):
    from general_tools.codex_tools import tool_write_file
    return _codex_handler_for(tool_write_file)


def make_list_directory_handler(bindings: dict):
    from general_tools.codex_tools import tool_list_directory
    return _codex_handler_for(tool_list_directory)


def make_search_files_handler(bindings: dict):
    from general_tools.codex_tools import tool_search_files
    return _codex_handler_for(tool_search_files)


def make_grep_search_handler(bindings: dict):
    from general_tools.codex_tools import tool_grep_search
    return _codex_handler_for(tool_grep_search)


def make_apply_patch_handler(bindings: dict):
    from general_tools.codex_tools import tool_apply_patch
    return _codex_handler_for(tool_apply_patch)


def make_view_image_handler(bindings: dict):
    from general_tools.codex_tools import tool_view_image
    return _codex_handler_for(tool_view_image)


def make_current_time_handler(bindings: dict):
    from general_tools.codex_tools import tool_current_time
    return _codex_handler_for(tool_current_time)


def make_plan_handler(bindings: dict):
    from general_tools.codex_tools import tool_plan
    return _codex_handler_for(tool_plan)


def make_request_user_input_handler(bindings: dict):
    from general_tools.codex_tools import tool_request_user_input
    return _codex_handler_for(tool_request_user_input)


def make_spawn_agent_handler(bindings: dict):
    from general_tools.codex_tools import tool_spawn_agent
    return _codex_handler_for(tool_spawn_agent)


def make_wait_agent_handler(bindings: dict):
    from general_tools.codex_tools import tool_wait_agent
    return _codex_handler_for(tool_wait_agent)


def make_list_agents_handler(bindings: dict):
    from general_tools.codex_tools import tool_list_agents
    return _codex_handler_for(tool_list_agents)


def make_cancel_agent_handler(bindings: dict):
    from general_tools.codex_tools import tool_cancel_agent
    return _codex_handler_for(tool_cancel_agent)


def make_send_notification_handler(bindings: dict):
    from general_tools.codex_tools import tool_send_notification
    return _codex_handler_for(tool_send_notification)


def make_memory_read_handler(bindings: dict):
    from general_tools.codex_tools import tool_memory_read
    return _codex_handler_for(tool_memory_read)


def make_memory_write_handler(bindings: dict):
    from general_tools.codex_tools import tool_memory_write
    return _codex_handler_for(tool_memory_write)


def make_web_search_handler(bindings: dict):
    from general_tools.codex_tools import tool_web_search
    return _codex_handler_for(tool_web_search)
