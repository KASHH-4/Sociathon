"""
In-process SSE broadcaster.
Each device_id gets its own queue; the stream route pops from it.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Generator

_lock = threading.Lock()
_queues: dict[str, queue.Queue] = {}   # device_id → Queue


def _get_or_create(device_id: str) -> queue.Queue:
    with _lock:
        if device_id not in _queues:
            _queues[device_id] = queue.Queue(maxsize=50)
        return _queues[device_id]


def subscribe(device_id: str) -> Generator[str, None, None]:
    """Generator that yields SSE-formatted strings."""
    q = _get_or_create(device_id)
    last_heartbeat = time.time()
    try:
        while True:
            # Heartbeat every 15 seconds
            try:
                event = q.get(timeout=1.0)
                yield _format_sse(event["event"], event["data"])
            except queue.Empty:
                pass
            if time.time() - last_heartbeat >= 15:
                yield _format_sse("heartbeat", {"ts": int(time.time())})
                last_heartbeat = time.time()
    finally:
        # Clean up queue on disconnect
        with _lock:
            _queues.pop(device_id, None)


def push(device_id: str, event: str, data: dict[str, Any]) -> None:
    """Push an event to a device's SSE queue."""
    q = _get_or_create(device_id)
    try:
        q.put_nowait({"event": event, "data": data})
    except queue.Full:
        # Drop oldest and push new
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait({"event": event, "data": data})
        except queue.Full:
            pass


def broadcast(event: str, data: dict[str, Any]) -> None:
    """Push an event to all connected device queues."""
    with _lock:
        device_ids = list(_queues.keys())
    for device_id in device_ids:
        push(device_id, event, data)


def _format_sse(event: str, data: Any) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"
