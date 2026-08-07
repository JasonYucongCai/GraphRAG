"""
IPP_Social.util — tiny shared helpers.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

_tmp_counter = 0
_tmp_lock = threading.Lock()

# per-path locks: on Windows, os.replace fails (WinError 5/32) when
# another thread holds an open read handle on the destination, so every
# read/write of a mutable social-database file goes through these.
_path_locks: dict[str, threading.RLock] = {}
_path_locks_guard = threading.Lock()


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _path_locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = _path_locks[key] = threading.RLock()
        return lock


def now_iso() -> str:
    """Timestamp in the repo's ``%Y-%m-%dT%H:%M:%S`` convention."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def slugify(text: str, fallback: str = "item") -> str:
    """kebab-case slug for ids."""
    out = "".join(c if (c.isalnum() or c in "-_") else "-"
                  for c in str(text).strip().lower())
    out = "-".join(p for p in out.split("-") if p)
    return out or fallback


def read_text(path: Path | str) -> str:
    """Locked read (pairs with atomic_write on the same path)."""
    p = Path(path)
    with _path_lock(p):
        return p.read_text(encoding="utf-8")


def atomic_write(path: Path | str, text: str) -> None:
    """Locked write via a unique temp file + atomic replace.

    The temp name is unique per call (pid + counter) so concurrent
    writers never collide on a shared ``.tmp`` name; ``os.replace`` is
    atomic (last writer wins) and retried on transient Windows locks.
    """
    global _tmp_counter
    p = Path(path)
    with _tmp_lock:
        _tmp_counter += 1
        seq = _tmp_counter
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{seq}.tmp")
    with _path_lock(p):
        tmp.write_text(text, encoding="utf-8")
        for attempt in range(6):
            try:
                os.replace(tmp, p)
                return
            except OSError:
                if attempt >= 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
