"""
IPP_Social.errors — shared domain errors for the social layer.

Every module raises ``SocialError`` subclasses; the IPP handlers
translate them into structured ``{"ok": false, "error": <code>, ...}``
payloads at the component boundary.
"""
from __future__ import annotations


class SocialError(Exception):
    """Base error; ``code`` is the machine-readable ``error`` field."""

    code = "social_error"

    def __init__(self, message: str, **extra):
        super().__init__(message)
        if "code" in extra:          # instance-level error code wins
            self.code = extra.pop("code")
        self.extra = extra

    def as_payload(self) -> dict:
        return {"ok": False, "error": self.code, "message": str(self),
                **self.extra}


class ConstraintViolation(SocialError):
    code = "constraint_violation"


class ModeNotAllowed(SocialError):
    code = "mode_not_allowed"


class UnknownAgent(SocialError):
    code = "unknown_agent"


class DuplicateAgent(SocialError):
    code = "duplicate_agent"


class DuplicateGoal(SocialError):
    code = "duplicate_goal"


class UnknownGoal(SocialError):
    code = "unknown_goal"


class UnknownTask(SocialError):
    code = "unknown_task"


class InvalidStatus(SocialError):
    code = "invalid_status"
