"""Inter-process mutual exclusion for steward critical sections.

Multiple CLI processes (sessions, subagents, watchdog) may submit concurrently.
An exclusive flock on <root>/.steward.lock serializes them; this IS the
serialized queue — Jev gating happens inside the lock so version checks and
commits can never interleave.
"""
from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager

LOCK_FILE = ".steward.lock"


@contextmanager
def exclusive(root: str, timeout: float = 120.0):
    """Block until the store-wide exclusive lock is acquired."""
    fd = os.open(os.path.join(root, LOCK_FILE), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
