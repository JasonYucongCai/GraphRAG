"""
ui.gradio_chat — the Gradio chat interface for the three codex agents.

A traditional chat UI you can talk to for general tasks (codex_normal), for
questions about the knowledge network (codex_RAG), or to grow the network
(codex_growth).

Run:
    python ui/gradio_chat.py                 # → http://127.0.0.3:7860
    python ui/gradio_chat.py --agent codex_RAG   # pick a default agent
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent
if str(_WS) not in sys.path:
    sys.path.insert(0, str(_WS))

import gradio as gr  # noqa: E402

from general_tools.config import Config  # noqa: E402
from general_tools.graph import KnowledgeGraph  # noqa: E402
from general_tools.encoder import EncoderLayer  # noqa: E402
from LLMs import llm_node as _llm_node  # noqa: E402 — LLM IPP node
from database.notes import NoteStore  # noqa: E402
from general_tools.construct import tools_node as _shared_tools_node
from codex_growth import create_agent as make_growth  # noqa: E402
from codex_RAG import create_agent as make_rag  # noqa: E402
from codex_normal import create_agent as make_normal  # noqa: E402

logging.basicConfig(level=logging.WARNING)


def _make_provider():
    """Construct the shared LLM IPP node."""
    node = _llm_node()
    try:
        node.invoke("chat", {"messages": [{"role": "user", "content": "ping"}], "max_tokens": 4})
        logger.info("LLM provider: live (via IPP node)")
    except Exception as exc:
        logger.warning("DeepSeek unavailable (%s)", exc)
    return node


def load_graph():
    graph = KnowledgeGraph()
    encoder = EncoderLayer()
    if graph.path.exists() and (Config.VECTOR_DIR / "index.json").exists():
        graph.load()
        encoder.load()
    else:
        from general_tools.build import build_graph
        graph, encoder = build_graph()
    graph.pagerank()
    return graph, encoder


def _load():
    graph, encoder = load_graph()
    store = NoteStore()
    active = store.active_project()
    if active:
        try:
            store.open_project(active)
            store.load_to_graph(graph)
            graph.pagerank()
        except ValueError:
            pass
    _shared_tools_node()
    ensure_shared_tools()
    llm = _make_provider()
    agents = {
        # chat surface is READ-ONLY: file-write + graph-mutation tools disabled
        "codex_growth": make_growth(graph, encoder, llm_node=llm, store=store, chat_mode=True),
        "codex_RAG": make_rag(graph, encoder, llm_node=llm, store=store, chat_mode=True),
        "codex_normal": make_normal(graph, encoder, llm_node=llm, store=store, chat_mode=True),
    }
    return agents, store


_AGENTS, _STORE = _load()
PROVIDER = getattr(_AGENTS["codex_normal"], "llm", None)


def _process_markdown(trace: list[dict]) -> str:
    """Render the full agentic process as foldable HTML blocks (ChatGPT-style)."""
    if not trace:
        return ""
    lines = ["<details open><summary>🔄 Agentic process</summary>"]
    for step in trace:
        t = step.get("type")
        if t == "thinking":
            lines.append(f"<details><summary>🧠 thinking</summary>\n\n{step.get('content','')}\n\n</details>")
        elif t == "message":
            lines.append(f"<details><summary>💬 message</summary>\n\n{step.get('content','')}\n\n</details>")
        elif t == "tool_call":
            args = step.get("args") or {}
            lines.append(f"<details><summary>🛠 {step.get('tool')}({args})</summary>")
        elif t == "tool_result":
            lines.append(f"\n```\n{step.get('content','')[:4000]}\n```\n</details>")
    lines.append("</details>")
    return "\n".join(lines)


def _run(agent_id: str, message: str, node: str):
    """
    Run one message through the selected agent, STREAMING the process.

    Yields (process_html, answer) repeatedly as events arrive:
      - process_html grows with each thinking/message/tool step
      - answer grows as the final answer is streamed in
    """
    engine = _AGENTS[agent_id]
    if node.strip():
        engine.bind_node(node.strip())
    trace: list[dict] = []
    answer = ""
    try:
        for event in engine.chat_stream(message):
            if event.type in ("thinking", "message", "tool_call", "tool_result"):
                entry = {"type": event.type}
                if event.tool is not None:
                    entry["tool"] = event.tool
                if event.args is not None:
                    entry["args"] = event.args
                entry["content"] = event.content or ""
                trace.append(entry)
                yield _process_markdown(trace), answer
            elif event.type == "message_delta":
                answer += event.content or ""
                yield _process_markdown(trace), answer
            elif event.type == "text":
                answer += event.content or ""
                yield _process_markdown(trace), answer
    except Exception as exc:  # noqa: BLE001
        yield "", f"[error] {exc}"


def respond(message, history, agent_id, node):
    history = list(history)
    history.append({"role": "user", "content": message})
    reply = ""
    process = ""
    for proc, ans in _run(agent_id, message, node or ""):
        process, reply = proc, ans
        combined = f"{process}\n\n---\n\n{reply}" if process else reply
        history = history[:-1] if history and history[-1]["role"] == "assistant" else history
        yield history + [{"role": "assistant", "content": combined}], ""
    combined = f"{process}\n\n---\n\n{reply}" if process else reply
    yield history + [{"role": "assistant", "content": combined}], ""


def build_demo(default_agent: str = "codex_normal"):
    with gr.Blocks(title="Codex Agents — Graph Knowledge Network") as demo:
        gr.Markdown(
            "# 🤖 Codex Agents — Graph Knowledge Network\n"
            "Chat with the agents. `codex_normal` does general tasks; "
            "`codex_RAG` answers questions about the knowledge network; "
            "`codex_growth` improves notes & expands the network "
            "(give it an anchor node + topic).")
        with gr.Row():
            agent_sel = gr.Dropdown(
                choices=["codex_normal", "codex_RAG", "codex_growth"],
                value=default_agent, label="Agent")
            node_box = gr.Textbox(
                label="Anchor node / context",
                placeholder="e.g. agent_memory, peng_survey, hybrid_rag … (for RAG & growth)")
        chatbot = gr.Chatbot(height=480)
        with gr.Row():
            msg = gr.Textbox(placeholder="Ask the agent…", scale=6, container=False)
            send = gr.Button("Send", variant="primary")
        clear = gr.Button("Clear")
        state = gr.State([])

        send.click(respond, [msg, state, agent_sel, node_box], [chatbot, msg])
        msg.submit(respond, [msg, state, agent_sel, node_box], [chatbot, msg])
        clear.click(lambda: ([], ""), None, [chatbot, state])
    return demo


def main(host: str = "127.0.0.3", port: int = 7860, default_agent: str = "codex_normal"):
    demo = build_demo(default_agent)
    demo.launch(server_name=host, server_port=port, share=False,
                theme=gr.themes.Soft())


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Gradio chat for the codex agents")
    p.add_argument("--host", default="127.0.0.3")
    p.add_argument("--port", type=int, default=7860)
    p.add_argument("--agent", default="codex_normal",
                   choices=["codex_normal", "codex_RAG", "codex_growth"])
    a = p.parse_args()
    main(a.host, a.port, a.agent)
