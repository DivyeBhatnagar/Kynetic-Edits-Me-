"""
Phase 29 — Host Agent Idempotency Store (host_agent/idempotency_store.py)

Deduplicates control-plane commands by idempotency_key.
Ensures retried commands (due to network blips or timeouts) never re-execute
workloads or duplicate volume operations on the host.

Features:
  - In-memory set + ring buffer (default max capacity 10,000 keys)
  - Thread-safe / asyncio-safe checks
"""

import collections
import threading
from typing import Set

_MAX_KEYS = 10000
_lock = threading.Lock()
_seen_keys: Set[str] = set()
_key_fifo: collections.deque[str] = collections.deque()


def already_processed(idempotency_key: str) -> bool:
    """Check if the given idempotency_key has already been executed."""
    if not idempotency_key:
        return False
    with _lock:
        return idempotency_key in _seen_keys


def mark_processed(idempotency_key: str) -> None:
    """Mark an idempotency_key as processed."""
    if not idempotency_key:
        return
    with _lock:
        if idempotency_key in _seen_keys:
            return
        if len(_key_fifo) >= _MAX_KEYS:
            oldest = _key_fifo.popleft()
            _seen_keys.discard(oldest)
        _seen_keys.add(idempotency_key)
        _key_fifo.append(idempotency_key)


def clear_idempotency_store() -> None:
    """Clear memory store (used in unit tests)."""
    with _lock:
        _seen_keys.clear()
        _key_fifo.clear()
