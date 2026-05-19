"""GatewayClient — async WebSocket client for sb-orchestrator's gateway.

Speaks the wire protocol documented in `realtimeodds-spec/schemas/v1/wire/`:
performs the `hello` handshake, applies snapshots, then dispatches mutations
into per-source `OddsStore` instances.

This is internal — the public `Client` (in `realtimeodds.client`) wraps it
and translates wire events into the spec-level SDK events.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed

from .._emitter import TypedEmitter
from .._entities import sport_event_from_json
from .._store import OddsStore
from .._types import SelectionId, SportEventId
from .protocol import (
    SDK_PROTOCOL_VERSION,
    check_protocol_compatibility,
)
from .reconnect import ReconnectPolicy, compute_backoff_delay_ms

logger = logging.getLogger("realtimeodds.gateway")


class GatewayClient:
    """Async WebSocket client. Lifecycle is controlled via `connect()` / `disconnect()`.

    Events emitted on `self.events`:
      - `connected` (None)
      - `disconnected` ({will_reconnect, code, reason})
      - `reconnect_scheduled` ({attempt, delay_ms})
      - `exhausted` ({attempts, reason})
      - `incompatible` ({reason, server_version})
      - `warning` ({reason})
      - `error` (exception)
      - `source:added` ((source_id, store))
      - `source:cleared` (source_id)
      - `source:resynced` ((source_id, reason, store))
    """

    __slots__ = (
        "_attempt",
        "_handshake_done",
        "_open_task",
        "_pending_close_tasks",
        "_reconnect",
        "_reconnect_task",
        "_recv_task",
        "_running",
        "_stores",
        "_url",
        "_ws",
        "events",
    )

    def __init__(self, url: str, reconnect: ReconnectPolicy | None = None) -> None:
        self._url = url
        self._reconnect = reconnect or ReconnectPolicy()
        self._running = False
        self._handshake_done = False
        self._ws: ClientConnection | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._open_task: asyncio.Task[None] | None = None
        self._pending_close_tasks: list[asyncio.Task[None]] = []
        self._attempt = 0
        self._stores: dict[str, OddsStore] = {}
        self.events = TypedEmitter()

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Idempotent: schedule a connection attempt and return immediately.

        The actual TCP/WS open happens in a background task. Subscribe to
        the `connected` event (or `error` with `fatal=True`) for status.
        """
        if self._running:
            return
        self._running = True
        self._attempt = 0
        self._open_task = asyncio.create_task(self._open_socket())

    async def disconnect(self) -> None:
        """Cleanly stop and close. Idempotent."""
        self._running = False
        self._handshake_done = False
        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._recv_task is not None and not self._recv_task.done():
            self._recv_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close(code=1000, reason="client disconnect")
            except Exception:
                pass
        self._ws = None

    def get_stores(self) -> dict[str, OddsStore]:
        return self._stores

    def get_or_create_store(self, source: str) -> OddsStore:
        store = self._stores.get(source)
        if store is None:
            store = OddsStore()
            self._stores[source] = store
            self.events.emit("source:added", (source, store))
        return store

    # ─── Internals ──────────────────────────────────────────────────────────

    async def _open_socket(self) -> None:
        try:
            # `max_size` lifted from the websockets default of 1 MiB. The
            # initial `snapshot` frame can grow well past that for active
            # books (a single bookmaker covering NBA + several leagues
            # easily exceeds 1 MiB once player props ship). 16 MiB is the
            # safety ceiling; anything larger crosses into "your snapshot is
            # too big, paginate it" territory rather than "raise the limit".
            self._ws = await ws_connect(self._url, max_size=16 * 1024 * 1024)
        except Exception as err:
            self.events.emit("error", err)
            await self._on_close(code=0, reason=str(err))
            return

        self._handshake_done = False
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        ws = self._ws
        try:
            async for raw in ws:
                self._handle_raw(raw)
        except ConnectionClosed as cc:
            await self._on_close(code=cc.code, reason=cc.reason or "")
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.events.emit("error", err)
            await self._on_close(code=0, reason=str(err))

    async def _on_close(self, *, code: int, reason: str) -> None:
        # Auth-fatal codes stop reconnect.
        if code in (4001, 4002, 4003):
            self._running = False
        will_reconnect = self._running
        self._handshake_done = False
        self.events.emit(
            "disconnected", {"will_reconnect": will_reconnect, "code": code, "reason": reason}
        )
        self._ws = None
        if will_reconnect:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._attempt += 1
        if self._attempt > self._reconnect.max_attempts:
            self._running = False
            self.events.emit(
                "exhausted",
                {
                    "attempts": self._attempt,
                    "reason": f"max reconnect attempts ({self._reconnect.max_attempts}) exceeded",
                },
            )
            return
        delay_ms = compute_backoff_delay_ms(self._attempt, self._reconnect)
        self.events.emit("reconnect_scheduled", {"attempt": self._attempt, "delay_ms": delay_ms})
        self._reconnect_task = asyncio.create_task(self._reconnect_after(delay_ms / 1000.0))

    async def _reconnect_after(self, delay_seconds: float) -> None:
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        if self._running:
            await self._open_socket()

    # ─── Message dispatch ───────────────────────────────────────────────────

    def _handle_raw(self, raw: str | bytes) -> None:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            msg = json.loads(text)
        except Exception as err:
            self.events.emit("error", err)
            return
        if not self._handshake_done:
            self._handle_handshake(msg)
            return
        try:
            self._dispatch(msg)
        except Exception as err:
            self.events.emit("error", err)

    def _handle_handshake(self, msg: dict[str, Any]) -> None:
        if msg.get("type") != "hello":
            reason = (
                f"First message was {msg.get('type')!r}, expected 'hello'. "
                "Refusing connection per PROTOCOL.md."
            )
            self._refuse(reason)
            return
        server_version = msg.get("data", {}).get("protocolVersion", "")
        result = check_protocol_compatibility(server_version, SDK_PROTOCOL_VERSION)
        if result.kind == "incompatible":
            self._refuse(result.reason, server_version)
            return
        if result.kind == "warning":
            self.events.emit("warning", {"reason": result.reason})
        self._handshake_done = True
        self._attempt = 0
        self.events.emit("connected", None)

    def _refuse(self, reason: str, server_version: str = "") -> None:
        self._running = False
        if self._ws is not None:
            try:
                # Schedule close without awaiting; we're in a sync context.
                close_task = asyncio.create_task(self._ws.close(code=4000, reason=reason))
                self._pending_close_tasks.append(close_task)
                close_task.add_done_callback(self._pending_close_tasks.remove)
            except Exception:
                pass
        self.events.emit("incompatible", {"reason": reason, "server_version": server_version})

    def _dispatch(self, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "snapshot":
            for entry in msg.get("data", []):
                source = entry.get("source")
                if source is None:
                    continue
                payload = {k: v for k, v in entry.items() if k != "source"}
                store = self.get_or_create_store(source)
                store.upsert_sport_event(sport_event_from_json(payload))
            return
        if msg_type in ("new_event", "update_event"):
            source = msg.get("source")
            if source is None:
                return
            store = self.get_or_create_store(source)
            store.upsert_sport_event(sport_event_from_json(msg["data"]))
            return
        if msg_type == "prices_updated":
            source = msg.get("source")
            if source is None:
                return
            store = self.get_or_create_store(source)
            data = msg["data"]
            prices: dict[SelectionId, float] = {}
            for p in data.get("prices", []):
                prices[SelectionId(str(p["selectionId"]))] = float(p["price"])
            store.update_prices(SportEventId(str(data["sportEventId"])), prices)
            return
        if msg_type == "remove_event":
            source = msg.get("source")
            if source is None:
                return
            store = self.get_or_create_store(source)
            store.remove_sport_event(SportEventId(str(msg["data"]["sportEventId"])))
            return
        if msg_type == "store_cleared":
            source = msg.get("source")
            if source is None:
                return
            existing = self._stores.get(source)
            if existing is not None:
                existing.clear()
                self.events.emit("source:cleared", source)
            return
        if msg_type == "resync":
            source = msg.get("source")
            if source is None:
                return
            reason = str(msg.get("reason", ""))
            store = self.get_or_create_store(source)
            # Atomic full-state replacement: rebuild SportEvent instances from
            # the wire payload and swap the store's contents in one shot.
            events = [sport_event_from_json(raw) for raw in msg.get("data", [])]
            store.replace_with_snapshot(events)
            self.events.emit("source:resynced", (source, reason, store))
            return
        if msg_type == "hello":
            # Unexpected post-handshake hello — ignore silently.
            return
        # Unknown type: ignore (forward-compat).
