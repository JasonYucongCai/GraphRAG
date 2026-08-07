"""
chat_board — the global chat board.

One shared board where agents post messages visible to every other
agent. Data lives in the social database (``social_database/chat/
board.jsonl``). A post also fans out push notifications to subscribers
(the only push source — see ``a2a.push``).
"""
from __future__ import annotations

from IPP_Social.chat_board.board import ChatBoard, Message

__all__ = ["ChatBoard", "Message"]
