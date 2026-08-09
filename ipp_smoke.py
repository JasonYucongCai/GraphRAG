"""Smoke test for the IPP core runtime (temporary; superseded by real nodes)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from IPP import IPPFile, IPPConstructor, GraphContext, IPPValidationError, verify_node

SCHEMA_URI = "https://ipp-spec.org/v0.2.8/schema.json"


def _demo_handler(payload, context):
    return {"echo": payload}


DEMO_FILE = {
    "$schema": SCHEMA_URI,
    "ipp_version": "0.2.8",
    "node_id": "demo",
    "channels": [{
        "channel_id": "echo",
        "handler": "IPP_smoke:_demo_handler",
        "ipp_object": {
            "input": {"logical_type": "any", "description": "anything"},
            "process": {"description": "echo the payload"},
            "output": {"logical_type": "any", "description": "same payload"},
        },
        "ipp_executor": {
            "integrity": {"checksum_algorithm": "sha256",
                          "signature_required": False,
                          "verification_endpoint": None,
                          "payload_validation_schema": None},
            "policy": {"max_cost_per_call_usd": 0, "max_latency_ms": 1000,
                       "rate_limit_rps": 0, "security_clearance": "",
                       "retry_policy": {"max_retries": 0,
                                        "backoff_strategy": "constant"}},
            "provenance": {"audit_level": "full", "log_endpoint": "",
                           "chain_of_custody": True},
            "error_handling": {
                "fallback_nodes": [],
                "circuit_breaker": {"failure_threshold": 5,
                                    "recovery_timeout_ms": 30000},
                "escalation_policy": {"max_escalation_depth": 1,
                                      "escalation_delay_ms": 0}},
            "edge_capabilities": {
                "upstream_compatible": [],
                "downstream_compatible": [],
                "routing_modes": ["unicast"],
                "constraint_envelope": {
                    "max_parallel_edges": 1, "acknowledgment": "optional",
                    "backpressure_modes": ["block"],
                    "resolution_policy": "constructor_resolved"},
            },
        },
    }],
}


def _ground(payload, context):
    return {"task": f"[grounded] {payload['task']}"}


def _chat(payload, context):
    return {"answer": f"ANSWER({payload['task']})"}


def main():
    f = IPPFile.from_dict(DEMO_FILE)
    g = IPPConstructor(GraphContext())
    node = g.construct(f)
    print(node.summary())
    out = node.invoke("echo", "hello")
    print("output:", out.payload)
    print("record keys:", sorted(out.record.keys()))
    print("audit chain ok:", node.executors["echo"].audit_verify())
    print("verify:", verify_node(node) or "ALL 17 OK")

    # R1 violation must be rejected
    bad = dict(DEMO_FILE)
    bad["internal_topology"] = {"edges": [{
        "from": {"channel_id": "echo", "port": "input"},
        "to": {"channel_id": "echo", "port": "input"},
        "mode": "blocking"}]}
    try:
        IPPFile.from_dict(bad)
        print("BAD: R1 not caught")
    except IPPValidationError as e:
        print("R1 caught OK:", str(e)[:70])

    # X6: topology writes forbidden
    try:
        node.executors["echo"].set_topology()
        print("BAD: X6 not enforced")
    except PermissionError:
        print("X6 enforced OK (set_topology raises)")

    # two-channel pipeline with internal edge ground -> echo (blocking)
    f2_raw = {
        "$schema": SCHEMA_URI, "ipp_version": "0.2.8", "node_id": "pipe",
        "channels": [
            {"channel_id": "ground", "handler": "IPP_smoke:_ground",
             "ipp_object": {"input": {"logical_type": "task",
                                        "description": "task"},
                             "process": {"description": "prefix"},
                             "output": {"logical_type": "task",
                                         "description": "grounded task"}},
             "ipp_executor": dict(DEMO_FILE["channels"][0]["ipp_executor"])},
            {"channel_id": "chat", "handler": "IPP_smoke:_chat",
             "ipp_object": {"input": {"logical_type": "task",
                                        "description": "grounded task"},
                             "process": {"description": "chat"},
                             "output": {"logical_type": "answer",
                                         "description": "answer"}},
             "ipp_executor": dict(DEMO_FILE["channels"][0]["ipp_executor"])},
        ],
        "internal_topology": {"edges": [{
            "from": {"channel_id": "ground", "port": "output"},
            "to": {"channel_id": "chat", "port": "input"},
            "mode": "blocking", "timeout_ms": 5000}]},
    }

    def _ground(payload, context):
        return {"task": f"[grounded] {payload['task']}"}

    def _chat(payload, context):
        return {"answer": f"ANSWER({payload['task']})"}

    def _ground(payload, context):
        return {"task": f"[grounded] {payload['task']}"}

    def _chat(payload, context):
        return {"answer": f"ANSWER({payload['task']})"}

    f2 = IPPFile.from_dict(f2_raw)
    node2 = g.construct(f2)
    res = node2.invoke("ground", {"task": "hi"})
    print("\npipeline ground->chat result:", res.payload)
    print("internal traversal recorded:",
          node2.executors["chat"].audit_log[-1]["source"], "|",
          node2.executors["chat"].audit_log[-1]["source_channel"])
    print("chat audit chain ok:", node2.executors["chat"].audit_verify())
    print("pipe verify:", verify_node(node2) or "ALL 17 OK")


if __name__ == "__main__":
    main()
