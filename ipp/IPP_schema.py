"""
ipp.IPP_schema — the formal JSON Schema of an IPP v0.2.8 Json File (F).

Mirrors §9 of IPP_v0.2.8_Specification.md. Used by ipp.IPP_file to validate
every IPP Json File at construction time (before Γ parses it).

Pragmatic extension (documented): each channel may carry a ``"handler"``
field — an import-path declaration (e.g. ``"LLMs.IPP_object:make_chat_handler"``)
telling the Constructor Γ where to bind the runtime handler for that channel.
This is a *binding reference*, not runtime logic — the file stays declarative
(Invariant I1: no callable code inside F).
"""

IPP_SCHEMA_URI = "https://ipp-spec.org/v0.2.8/schema.json"
IPP_VERSION = "0.2.8"

IPP_JSON_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "IPP v0.2.8 Json File",
    "type": "object",
    "required": ["$schema", "ipp_version", "node_id", "channels"],
    "properties": {
        "$schema": {"const": IPP_SCHEMA_URI},
        "ipp_version": {"const": IPP_VERSION},
        "node_id": {"type": "string", "minLength": 1},
        "channels": {
            "type": "array", "minItems": 1,
            "items": {"$ref": "#/definitions/channel"},
        },
        "internal_topology": {"$ref": "#/definitions/internal_topology"},
    },
    "definitions": {
        "port": {
            "type": "object",
            "required": ["logical_type", "description"],
            "properties": {
                "logical_type": {"type": "string"},
                "description": {"type": "string"},
                "schema": {"type": ["object", "null"]},   # Λ6 template
            },
        },
        "channel": {
            "type": "object",
            "required": ["channel_id", "ipp_object", "ipp_executor"],
            "properties": {
                "channel_id": {"type": "string", "minLength": 1},
                "handler": {"type": "string", "minLength": 1},  # binding ref for Γ
                "ipp_object": {
                    "type": "object",
                    "required": ["input", "process", "output"],
                    "properties": {
                        "input": {"$ref": "#/definitions/port"},
                        "process": {
                            "type": "object",
                            "required": ["description"],
                            "properties": {
                                "description": {"type": "string"},
                                "kind": {"type": "string", "enum": [
                                    "llm", "deterministic", "agent", "tool"]},
                            },
                        },
                        "output": {"$ref": "#/definitions/port"},
                    },
                },
                "ipp_executor": {
                    "type": "object",
                    "required": ["integrity", "policy", "provenance",
                                 "error_handling", "edge_capabilities"],
                    "properties": {
                        "integrity": {
                            "type": "object",
                            "properties": {
                                "checksum_algorithm": {"enum": [
                                    "sha256", "sha512", "blake3"]},
                                "signature_required": {"type": "boolean"},
                                "verification_endpoint": {
                                    "type": ["string", "null"]},
                                "payload_validation_schema": {
                                    "type": ["object", "null"]},
                            },
                        },
                        "policy": {
                            "type": "object",
                            "properties": {
                                "max_cost_per_call_usd": {"type": "number",
                                                           "minimum": 0},
                                "max_latency_ms": {"type": "integer", "minimum": 1},
                                "rate_limit_rps": {"type": "integer", "minimum": 0},
                                "security_clearance": {"type": "string"},
                                "retry_policy": {
                                    "type": "object",
                                    "required": ["max_retries", "backoff_strategy"],
                                    "properties": {
                                        "max_retries": {"type": "integer",
                                                        "minimum": 0},
                                        "backoff_strategy": {"enum": [
                                            "constant", "exponential", "jitter"]},
                                    },
                                },
                            },
                        },
                        "provenance": {
                            "type": "object",
                            "properties": {
                                "audit_level": {"enum": ["none", "summary",
                                                          "full"]},
                                "log_endpoint": {"type": "string"},
                                "chain_of_custody": {"type": "boolean"},
                            },
                        },
                        "error_handling": {
                            "type": "object",
                            "properties": {
                                "fallback_nodes": {"type": "array",
                                                   "items": {"type": "string"}},
                                "circuit_breaker": {
                                    "type": "object",
                                    "required": ["failure_threshold",
                                                 "recovery_timeout_ms"],
                                    "properties": {
                                        "failure_threshold": {"type": "integer",
                                                              "minimum": 1},
                                        "recovery_timeout_ms": {"type": "integer",
                                                                "minimum": 1},
                                    },
                                },
                                "escalation_policy": {
                                    "type": "object",
                                    "properties": {
                                        "max_escalation_depth": {"type": "integer",
                                                                 "minimum": 0},
                                        "escalation_delay_ms": {"type": "integer",
                                                                "minimum": 0},
                                    },
                                },
                            },
                        },
                        "edge_capabilities": {
                            "type": "object",
                            "required": ["upstream_compatible",
                                         "downstream_compatible",
                                         "routing_modes",
                                         "constraint_envelope"],
                            "properties": {
                                "upstream_compatible": {
                                    "type": "array",
                                    "items": {"$ref": "#/definitions/edge_class"},
                                },
                                "downstream_compatible": {
                                    "type": "array",
                                    "items": {"$ref": "#/definitions/edge_class"},
                                },
                                "routing_modes": {"type": "array", "items": {
                                    "enum": ["unicast", "multicast", "broadcast",
                                             "anycast", "reduce"]}},
                                "constraint_envelope": {"$ref": "#/definitions/envelope"},
                            },
                        },
                    },
                },
            },
        },
        "edge_class": {
            "type": "object",
            "required": ["node_class", "edge_count_range", "compatibility"],
            "properties": {
                "node_class": {"type": "string"},
                "output_logical_type": {"type": "string"},
                "input_logical_type": {"type": "string"},
                "edge_count_range": {
                    "type": "object",
                    "required": ["min", "max"],
                    "properties": {
                        "min": {"type": "integer", "minimum": 0},
                        "max": {"type": "integer", "minimum": 0},
                    },
                },
                "compatibility": {"enum": ["exact", "convertible", "any"]},
            },
        },
        "envelope": {
            "type": "object",
            "required": ["max_parallel_edges", "acknowledgment",
                         "backpressure_modes", "resolution_policy"],
            "properties": {
                "max_parallel_edges": {"type": "integer", "minimum": 1},
                "acknowledgment": {"enum": ["optional", "required",
                                            "unsupported"]},
                "backpressure_modes": {"type": "array", "items": {
                    "enum": ["drop", "buffer", "block"]}},
                "resolution_policy": {"enum": ["constructor_resolved",
                                               "supervisor_guided", "open"]},
            },
        },
        "internal_topology": {
            "type": "object",
            "properties": {
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["from", "to", "mode"],
                        "properties": {
                            "from": {"$ref": "#/definitions/endpoint"},
                            "to": {"$ref": "#/definitions/endpoint"},
                            "mode": {"enum": ["blocking", "non_blocking",
                                              "callback"]},
                            "timeout_ms": {"type": "integer", "minimum": 1},
                        },
                    },
                },
            },
        },
        "endpoint": {
            "type": "object",
            "required": ["channel_id", "port"],
            "properties": {
                "channel_id": {"type": "string"},
                "port": {"enum": ["input", "output"]},
            },
        },
    },
}
