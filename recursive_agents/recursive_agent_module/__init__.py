"""
recursive_agent_module — IPP v0.2.8 node connecting the UI to recursive agents.

This is the SINGLE entry point. The Flask server never imports agent
internals — it only invokes channels on this node through the standard
IPP guardrail envelope:

    server.py  →  ra_node.invoke("instruct", {...})
                   └─> IPP_object.make_instruct_handler  (Ω)
                         └─> RecursiveAgentEngine         (loop)
                               └─> agent tools             (hands)

No direct imports of agent_a1/agent_a2 internals from the UI layer.
"""
from .IPP_object import bind
from .IPP_executor import RecursiveAgentExecutor
