"""Typed event emitter — synchronous callback dispatch.

Sync-only: callbacks fire in the order they were registered, on the same
task as the caller of `emit`. Async users wrap their handler in a coroutine
and `asyncio.create_task` if they need to await something.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class TypedEmitter:
    """A simple multi-listener event emitter keyed by event name (str).

    Designed for the small fixed set of `ClientEvent` names the SDK exposes;
    each event has its own payload type which `Client` constrains via
    `Generic` aliases.
    """

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[Any], None]]] = {}

    def on(self, event: str, listener: Callable[[Any], None]) -> None:
        self._listeners.setdefault(event, []).append(listener)

    def off(self, event: str, listener: Callable[[Any], None]) -> None:
        listeners = self._listeners.get(event)
        if listeners is None:
            return
        try:
            listeners.remove(listener)
        except ValueError:
            pass

    def emit(self, event: str, payload: Any) -> None:
        listeners = self._listeners.get(event)
        if not listeners:
            return
        # Iterate over a snapshot in case a listener mutates the registry.
        for listener in tuple(listeners):
            try:
                listener(payload)
            except Exception:
                # Don't let one bad handler poison the rest. The SDK does not
                # log here; consumers wrap their listener if they want logging.
                pass

    def remove_all(self, event: str | None = None) -> None:
        if event is None:
            self._listeners.clear()
        else:
            self._listeners.pop(event, None)
