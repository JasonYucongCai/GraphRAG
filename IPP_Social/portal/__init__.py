"""
portal — the Multi Agent portal node (IPP v0.2.8).

The user's window into the social network: discover (agents, goals,
cards, status), command (name a goal, give instructions through the
social network and to individual agents), monitor (live activity
stream), and swarm (start/stop the concurrent agent team).
"""
from __future__ import annotations

from IPP_Social.portal.construct import create_portal_node
from IPP_Social.portal.IPP_executor import PortalExecutor

__all__ = ["create_portal_node", "PortalExecutor"]
