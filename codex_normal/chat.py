"""
codex_normal/chat.py — the traditional Gradio chat for the general agent.

Talk to codex_normal for general tasks. The same app also lets you switch to
codex_RAG (questions about the network) and codex_growth (network growth).

Run:
    python codex_normal/chat.py             # → http://127.0.0.3:7860
"""
from __future__ import annotations

import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent
if str(_WS) not in sys.path:
    sys.path.insert(0, str(_WS))

from ui.gradio_chat import main  # noqa: E402

if __name__ == "__main__":
    main(default_agent="codex_normal")
