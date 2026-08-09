"""
agents.agent_card — the Agent Card (the discovery surface).

One card per agent; the card bundles the three properties (capacity,
random property, constraints) with discovery metadata. Cards are
**editable by other agents**: ``add_comment`` appends an annotation
(author, text, ts), bumps the card version, and logs to the card's VCL.
"""
from __future__ import annotations

from ManyAgents.agent_management.capacity import Capacity
from ManyAgents.agent_management.constraints import Constraints
from ManyAgents.agent_management.random_property import RandomProperty
from IPP_Social.util import now_iso


class Comment:
    """An annotation another agent left on a card."""

    def __init__(self, author_id: str, text: str, ts: str | None = None):
        self.author_id = author_id
        self.text = text
        self.ts = ts or now_iso()

    def to_dict(self) -> dict:
        return {"author_id": self.author_id, "text": self.text, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Comment":
        return cls(author_id=d.get("author_id", ""),
                   text=d.get("text", ""), ts=d.get("ts"))


class AgentCard:
    """The discoverable identity of a social agent (one JSON file)."""

    def __init__(self, agent_id: str, name: str,
                 capacity: Capacity | None = None,
                 random_property: RandomProperty | None = None,
                 constraints: Constraints | None = None,
                 bio: str = "", status: str = "active",
                 comments: list | None = None, version: int = 1,
                 vcl: list | None = None,
                 created: str | None = None, updated: str | None = None):
        self.agent_id = agent_id
        self.name = name
        self.capacity = capacity or Capacity()
        self.random_property = random_property or RandomProperty()
        self.constraints = constraints or Constraints()
        self.bio = bio
        self.status = status
        self.comments: list[Comment] = list(comments or [])
        self.version = int(version)
        self.vcl: list[str] = list(vcl or [])
        self.created = created or now_iso()
        self.updated = updated or self.created

    def to_dict(self) -> dict:
        """The card JSON: the three properties + discovery + comments."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "bio": self.bio,
            "status": self.status,
            # ── the three properties ──
            "capacity": self.capacity.to_dict(),
            "random_property": self.random_property.to_dict(),
            "constraints": self.constraints.to_dict(),
            # ── discovery / annotations ──
            "comments": [c.to_dict() for c in self.comments],
            "version": self.version,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentCard":
        return cls(
            agent_id=d.get("agent_id", ""),
            name=d.get("name", ""),
            capacity=Capacity.from_dict(d.get("capacity")),
            random_property=RandomProperty.from_dict(d.get("random_property")),
            constraints=Constraints.from_dict(d.get("constraints")),
            bio=d.get("bio", ""),
            status=d.get("status", "active"),
            comments=[Comment.from_dict(c) for c in d.get("comments", [])],
            version=int(d.get("version", 1)),
            vcl=list(d.get("vcl", [])),
            created=d.get("created"),
            updated=d.get("updated"),
        )

    # ── card editing by OTHER agents ─────────────────────────────────────
    def add_comment(self, author_id: str, text: str) -> None:
        """Annotate the card. Anyone may comment; capacity stays identity."""
        self.comments.append(Comment(author_id=author_id, text=text))
        self.bump(f"comment by {author_id}")

    def bump(self, note: str) -> None:
        self.version += 1
        self.updated = now_iso()
        self.vcl.append(f"{self.updated}: {note} (v{self.version})")
