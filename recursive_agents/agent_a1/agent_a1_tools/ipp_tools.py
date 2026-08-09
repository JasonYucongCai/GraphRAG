"""
agent_a1_tools.ipp_tools — IPP verification & construction tools (5 tools)

ipp_construct, ipp_verify, ipp_audit, ipp_status_report, ipp_check_invariants
"""
from __future__ import annotations
import json
from typing import Any
from .tool_base import ReadOnlyTool, ToolContext, ToolResult


class IPPConstructTool(ReadOnlyTool):
    tool_name = "ipp_construct"
    category = "ipp"
    description = "Construct IPP nodes from F-files through Γ (7-step protocol)."
    tool_schema = {
        "type": "object", "required": ["filePath"],
        "properties": {
            "filePath": {"type": "string", "description": "Path to IPP.json F-file."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.success("ipp_construct: use agent_create for full construction")


class IPPVerifyTool(ReadOnlyTool):
    tool_name = "ipp_verify"
    category = "ipp"
    description = "Verify ALL 17 IPP invariants for an agent node."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        tk = ctx.agent
        engine = tk.constructed.get(agent_id) if tk else None
        if engine is None:
            return ToolResult.fail(f"{agent_id} not constructed")
        try:
            from IPP.IPP_verify import verify_node
            ef = verify_node(engine.node)
            tf = verify_node(engine._tools_node)
            return ToolResult.success(
                f"{agent_id}: engine_invariants={'PASS' if not ef else list(ef)}, "
                f"tools_invariants={'PASS' if not tf else list(tf)}",
                engine_ok=(not ef), tools_ok=(not tf),
                engine_failures=list(ef) if ef else [],
                tools_failures=list(tf) if tf else [])
        except Exception as e:
            return ToolResult.fail(str(e))


class IPPAuditTool(ReadOnlyTool):
    tool_name = "ipp_audit"
    category = "ipp"
    description = "Verify hash-chained audit trails for an agent."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        tk = ctx.agent
        engine = tk.constructed.get(agent_id) if tk else None
        if engine is None:
            return ToolResult.fail(f"{agent_id} not constructed")
        try:
            e_audit = all(ex.audit_verify()
                         for ex in engine.node.executors.values())
            t_audit = all(ex.audit_verify()
                         for ex in engine._tools_node.executors.values())
            return ToolResult.success(
                f"{agent_id}: engine_audit={'OK' if e_audit else 'FAIL'}, "
                f"tools_audit={'OK' if t_audit else 'FAIL'}",
                engine_audit=e_audit, tools_audit=t_audit)
        except Exception as e:
            return ToolResult.fail(str(e))


class IPPStatusReportTool(ReadOnlyTool):
    tool_name = "ipp_status_report"
    category = "ipp"
    description = "Generate a full IPP status report for the agent chain."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        report = {
            "chain": list(tk.chain) if tk else [],
            "constructed": sorted(tk.constructed) if tk else [],
            "total_tools": tk.count() if hasattr(tk, 'count') else 0,
        }
        return ToolResult.success(json.dumps(report, ensure_ascii=False, indent=2),
                                  **report)


class IPPCheckInvariantsTool(ReadOnlyTool):
    tool_name = "ipp_check_invariants"
    category = "ipp"
    description = "Quick check: do ALL 17 invariants pass for EVERY constructed agent?"
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        if not tk:
            return ToolResult.fail("no toolkit")
        results = {}
        all_ok = True
        for name, engine in tk.constructed.items():
            try:
                from IPP.IPP_verify import verify_node
                ef = verify_node(engine.node)
                tf = verify_node(engine._tools_node)
                ok = (not ef and not tf)
                results[name] = ok
                if not ok:
                    all_ok = False
            except Exception:
                results[name] = False
                all_ok = False
        return ToolResult.success(
            f"ALL OK: {all_ok}" if all_ok else f"FAILURES: {results}",
            all_ok=all_ok, per_agent=results)


def register_ipp_tools(toolkit) -> None:
    toolkit.register_many([
        IPPConstructTool(), IPPVerifyTool(), IPPAuditTool(),
        IPPStatusReportTool(), IPPCheckInvariantsTool(),
    ])
