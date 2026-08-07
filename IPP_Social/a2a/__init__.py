"""
a2a — the four formal A2A interaction modes (A2A by Google).

All four modes are coded as formal methods:

  sync     SyncHandoff        declared, currently NOT allowed
  async    AsyncTask          allowed — task-based (submit + poll status)
  stream   StreamSubscription allowed — social event bus (buffered/live)
  push     PushNotification   allowed, scoped to the chat board only

The formal registry lives in ``a2a.modes``; ``execute_a2a`` dispatches.
"""
from __future__ import annotations

from IPP_Social.a2a.async_task import AsyncTask
from IPP_Social.a2a.modes import A2A_METHODS, A2A_MODES, A2AContext, execute_a2a
from IPP_Social.a2a.push import ALLOWED_PUSH_SCOPES, PushNotifier
from IPP_Social.a2a.stream import StreamSubscription
from IPP_Social.a2a.sync import SyncHandoff

__all__ = [
    "A2A_METHODS", "A2A_MODES", "A2AContext", "execute_a2a",
    "SyncHandoff", "AsyncTask", "StreamSubscription", "PushNotifier",
    "ALLOWED_PUSH_SCOPES",
]
