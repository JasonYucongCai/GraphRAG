"""
IPP.IPP_registry — the Graph Context 𝒢 (external, deployment-specific).

Per IPP v0.2.8 §3.2:

  𝒢 := (𝒩, ℰ_cand, 𝒫_sup)

  • 𝒩       — registry: available nodes with per-channel capability spaces
  • ℰ_cand  — candidate edge set: (node, channel) pairs whose capability
              spaces are mutually compatible
  • 𝒫_sup   — supervisor intent: deployment goals / wiring preferences

External topology is NOT declared in F — it is resolved here at
construction time (Theorem 6). Internal topology never consults 𝒢.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("IPP.IPP_registry")


class RegistryEntry:
    """A registered node with its per-channel capability spaces."""

    def __init__(self, node_id: str, channels: dict, node: Any = None):
        self.node_id = node_id
        self.channels: dict = channels      # {channel_id: {"in","out","caps"}}
        self.node = node                    # optional constructed IPPNode

    def capability(self, channel_id: str) -> dict:
        return self.channels.get(channel_id, {}).get("caps", {})

    def logical_out(self, channel_id: str) -> str:
        return self.channels.get(channel_id, {}).get("out", "")

    def logical_in(self, channel_id: str) -> str:
        return self.channels.get(channel_id, {}).get("in", "")


class GraphContext:
    """𝒢 — the deployment graph consulted by Γ for external resolution."""

    def __init__(self, supervisor: Optional[dict] = None):
        self.registry: dict[str, RegistryEntry] = {}
        self.supervisor: dict = supervisor or {}
        self._bindings: dict = {}           # constructor bindings (handlers)

    # ── registry 𝒩 ────────────────────────────────────────────────────────
    def register(self, node_id: str, channels: dict,
                 node: Any = None) -> RegistryEntry:
        entry = RegistryEntry(node_id, channels, node)
        self.registry[node_id] = entry
        return entry

    def register_node(self, node: Any) -> RegistryEntry:
        """Register a constructed IPPNode: per-channel port logical types +
        capability spaces (the 𝒩 registry entries)."""
        channels = {}
        for ch_id, ex in node.executors.items():
            channels[ch_id] = {
                "in": node.objects[ch_id].input_port.logical_type,
                "out": node.objects[ch_id].output_port.logical_type,
                "caps": ex.capabilities,
            }
        return self.register(node.node_id, channels, node)

    def get(self, node_id: str) -> Optional[RegistryEntry]:
        return self.registry.get(node_id)

    def bind(self, key: str, value: Any) -> None:
        """Bind an external dependency for handler factories (e.g. provider)."""
        self._bindings[key] = value

    @property
    def bindings(self) -> dict:
        return self._bindings

    # ── candidates ℰ_cand ─────────────────────────────────────────────────
    def candidates(self, cap: dict, direction: str) -> list[tuple[str, str]]:
        """Find (node_id, channel_id) partners compatible with `cap`'s
        upstream (direction='upstream') or downstream classes."""
        classes = cap.get(f"{direction}_compatible", [])
        out: list[tuple[str, str]] = []
        for entry in self.registry.values():
            for ch_id, ch_info in entry.channels.items():
                for cls in classes:
                    want_class = cls.get("node_class")
                    if want_class and want_class != "*" and \
                            want_class != entry.node_id:
                        continue
                    # logical-type match (exact | convertible | any)
                    if direction == "upstream":
                        want_lt = cls.get("output_logical_type")
                        peer_lt = ch_info.get("out", "")
                    else:
                        want_lt = cls.get("input_logical_type")
                        peer_lt = ch_info.get("in", "")
                    if not want_lt:
                        continue
                    compat = cls.get("compatibility", "any")
                    if compat == "any" or want_lt == peer_lt or \
                            compat == "convertible":
                        out.append((entry.node_id, ch_id))
                        break
        return out
