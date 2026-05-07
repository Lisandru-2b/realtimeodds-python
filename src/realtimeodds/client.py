"""Public Client — wraps the internal `GatewayClient` and exposes spec-level events.

Mirror of the JS port `realtimeodds/createClient`. Async-first: `connect()` is
awaitable and resolves on the first successful handshake (or raises on fatal).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlencode, urlparse, urlunparse

from ._emitter import TypedEmitter
from ._entities import Quote, SportEvent
from ._gateway import GatewayClient, ReconnectPolicy
from ._store import OddsStore
from ._types import Bookmaker, MarketId, SelectionId, SportEventId

ConnectionStatus = Literal["disconnected", "connecting", "connected", "reconnecting"]


@dataclass(frozen=True, slots=True)
class ConnectionState:
    status: ConnectionStatus
    last_error: Exception | None = None


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Current state of the SDK's mirrored stores. Marked `stale` when not connected."""

    sport_events: Mapping[SportEventId, SportEvent]
    stale: bool


# ─── Event payload dataclasses ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DisconnectedEvent:
    will_reconnect: bool
    code: int
    reason: str


@dataclass(frozen=True, slots=True)
class ReconnectingEvent:
    attempt: int
    delay_ms: int


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    message: str
    fatal: bool


@dataclass(frozen=True, slots=True)
class SportEventAddedEvent:
    sport_event: SportEvent
    received_at: int


@dataclass(frozen=True, slots=True)
class SportEventUpdatedEvent:
    sport_event: SportEvent
    received_at: int


@dataclass(frozen=True, slots=True)
class SportEventRemovedEvent:
    bookmaker: Bookmaker
    sport_event_id: SportEventId
    received_at: int


@dataclass(frozen=True, slots=True)
class OddsChangedEvent:
    bookmaker: Bookmaker
    sport_event_id: SportEventId
    market_id: MarketId
    selection_id: SelectionId
    quote: Quote
    received_at: int


# ─── Helpers ────────────────────────────────────────────────────────────────


def _append_api_key(url: str, api_key: str) -> str:
    parsed = urlparse(url)
    query = parsed.query
    extra = urlencode({"apiKey": api_key})
    if query:
        new_query = f"{query}&{extra}"
    else:
        new_query = extra
    return urlunparse(parsed._replace(query=new_query))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _describe_error(err: object) -> str:
    if err is None:
        return "Unknown error"
    if isinstance(err, BaseException):
        return str(err) or err.__class__.__name__
    if isinstance(err, str):
        return err or "Empty error string"
    return str(err)


# ─── Client ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _PendingConnect:
    future: asyncio.Future[None]


class Client:
    """The realtimeodds SDK client.

    Open the WebSocket with `await client.connect()`, subscribe to events with
    `client.on(name, callback)`. The client auto-reconnects with exponential
    backoff on transient drops.
    """

    __slots__ = (
        "_api_key",
        "_emitter",
        "_gw",
        "_pending",
        "_reconnect",
        "_state",
        "_url",
        "_wired_stores",
    )

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        reconnect: ReconnectPolicy | None = None,
    ) -> None:
        if not url:
            raise ValueError("url is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._url = url
        self._api_key = api_key
        self._reconnect = reconnect
        self._emitter = TypedEmitter()
        self._state: ConnectionState = ConnectionState(status="disconnected")
        self._gw: GatewayClient | None = None
        self._pending: _PendingConnect | None = None
        self._wired_stores: set[int] = set()

    # ─── Public surface ─────────────────────────────────────────────────────

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    def on(self, event: str, listener: Callable[[Any], None]) -> None:
        self._emitter.on(event, listener)

    def off(self, event: str, listener: Callable[[Any], None]) -> None:
        self._emitter.off(event, listener)

    async def connect(self) -> None:
        """Open the WebSocket. Resolves on first successful connection.

        Raises on fatal errors (invalid apiKey, exhausted reconnect attempts,
        incompatible protocol). Transient errors keep retrying — the coroutine
        stays pending until either success or fatal.

        Calling `connect()` while a connection attempt is in flight returns
        the same future. Calling after a successful connection resolves
        immediately.
        """
        if self._pending is not None:
            await self._pending.future
            return
        if self._state.status == "connected":
            return

        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        self._pending = _PendingConnect(future=future)

        url = _append_api_key(self._url, self._api_key)
        self._state = ConnectionState(status="connecting")

        gw = GatewayClient(url=url, reconnect=self._reconnect)
        self._gw = gw
        self._attach_gateway_handlers(gw)
        gw.connect()

        try:
            await future
        finally:
            self._pending = None

    async def disconnect(self) -> None:
        """Close and stop reconnecting. Idempotent.

        If a `connect()` is in flight, it will raise.
        """
        if self._pending is not None and not self._pending.future.done():
            self._pending.future.set_exception(
                RuntimeError("disconnect() called before connect() completed")
            )
        if self._gw is not None:
            await self._gw.disconnect()
            self._gw = None
        self._state = ConnectionState(status="disconnected")

    def snapshot(self) -> Snapshot:
        """Return a read-only mapping of every known sport event, keyed by id.

        `stale=True` when the connection is not currently established.
        """
        sport_events: dict[SportEventId, SportEvent] = {}
        if self._gw is not None:
            for store in self._gw.get_stores().values():
                for sport_event_id, sport_event in store.get_all_sport_events().items():
                    sport_events[sport_event_id] = sport_event
        return Snapshot(sport_events=sport_events, stale=self._state.status != "connected")

    def get_sport_event(self, sport_event_id: SportEventId) -> SportEvent | None:
        if self._gw is None:
            return None
        for store in self._gw.get_stores().values():
            sport_event = store.get_sport_event(sport_event_id)
            if sport_event is not None:
                return sport_event
        return None

    # ─── Gateway → public translation ────────────────────────────────────────

    def _attach_gateway_handlers(self, gw: GatewayClient) -> None:
        gw.events.on("connected", self._on_gw_connected)
        gw.events.on("disconnected", self._on_gw_disconnected)
        gw.events.on("reconnect_scheduled", self._on_gw_reconnect_scheduled)
        gw.events.on("exhausted", self._on_gw_exhausted)
        gw.events.on("incompatible", self._on_gw_incompatible)
        gw.events.on("error", self._on_gw_error)
        gw.events.on("source:added", self._on_gw_source_added)

    def _on_gw_connected(self, _payload: object) -> None:
        self._state = ConnectionState(status="connected")
        self._emitter.emit("connected", None)
        if self._pending is not None and not self._pending.future.done():
            self._pending.future.set_result(None)

    def _on_gw_disconnected(self, payload: dict[str, Any]) -> None:
        will_reconnect = bool(payload.get("will_reconnect", False))
        code = int(payload.get("code", 0))
        reason = str(payload.get("reason", ""))
        self._emitter.emit(
            "disconnected",
            DisconnectedEvent(will_reconnect=will_reconnect, code=code, reason=reason),
        )
        if code in (4001, 4002, 4003):
            from ._gateway.protocol import auth_close_message

            message = auth_close_message(code, reason)
            err = RuntimeError(message)
            self._state = ConnectionState(status="disconnected", last_error=err)
            self._emitter.emit("error", ErrorEvent(message=message, fatal=True))
            self._fail_pending(err)
            return
        if not will_reconnect:
            self._state = ConnectionState(status="disconnected")

    def _on_gw_reconnect_scheduled(self, payload: dict[str, Any]) -> None:
        self._state = ConnectionState(status="reconnecting")
        self._emitter.emit(
            "reconnecting",
            ReconnectingEvent(
                attempt=int(payload.get("attempt", 0)),
                delay_ms=int(payload.get("delay_ms", 0)),
            ),
        )

    def _on_gw_exhausted(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("reason", "exhausted"))
        err = RuntimeError(message)
        self._state = ConnectionState(status="disconnected", last_error=err)
        self._emitter.emit("error", ErrorEvent(message=message, fatal=True))
        self._fail_pending(err)

    def _on_gw_incompatible(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("reason", "incompatible"))
        err = RuntimeError(message)
        self._state = ConnectionState(status="disconnected", last_error=err)
        self._emitter.emit("error", ErrorEvent(message=message, fatal=True))
        self._fail_pending(err)

    def _on_gw_error(self, err: object) -> None:
        self._emitter.emit("error", ErrorEvent(message=_describe_error(err), fatal=False))

    def _on_gw_source_added(self, payload: tuple[str, OddsStore]) -> None:
        source, store = payload
        # Avoid double-wiring: the gateway re-emits source:added on lazy creation.
        sentinel = id(store)
        if sentinel in self._wired_stores:
            return
        self._wired_stores.add(sentinel)
        bookmaker: Bookmaker = source  # type: ignore[assignment]
        self._wire_store(store, bookmaker)

    def _wire_store(self, store: OddsStore, bookmaker: Bookmaker) -> None:
        def on_upserted(payload: object) -> None:
            from ._store import SportEventUpsertedPayload

            assert isinstance(payload, SportEventUpsertedPayload)
            received_at = _now_ms()
            if payload.is_new:
                self._emitter.emit(
                    "sportEvent:added",
                    SportEventAddedEvent(sport_event=payload.sport_event, received_at=received_at),
                )
            else:
                self._emitter.emit(
                    "sportEvent:updated",
                    SportEventUpdatedEvent(
                        sport_event=payload.sport_event, received_at=received_at
                    ),
                )

        def on_removed(payload: object) -> None:
            from ._store import SportEventRemovedPayload

            assert isinstance(payload, SportEventRemovedPayload)
            self._emitter.emit(
                "sportEvent:removed",
                SportEventRemovedEvent(
                    bookmaker=bookmaker,
                    sport_event_id=payload.sport_event_id,
                    received_at=_now_ms(),
                ),
            )

        def on_prices_updated(payload: object) -> None:
            from ._store import PricesUpdatedPayload

            assert isinstance(payload, PricesUpdatedPayload)
            received_at = _now_ms()
            updated = store.get_sport_event(payload.sport_event_id)
            if updated is not None:
                self._emitter.emit(
                    "sportEvent:updated",
                    SportEventUpdatedEvent(sport_event=updated, received_at=received_at),
                )
            for selection_id in payload.prices:
                market = store.get_market(selection_id)
                if market is None:
                    continue
                selection = market.get_selection(selection_id)
                if selection is None or selection.quote is None:
                    continue
                self._emitter.emit(
                    "odds:changed",
                    OddsChangedEvent(
                        bookmaker=bookmaker,
                        sport_event_id=payload.sport_event_id,
                        market_id=market.id,
                        selection_id=selection_id,
                        quote=selection.quote,
                        received_at=received_at,
                    ),
                )

        store.on("sportEvent:upserted", on_upserted)
        store.on("sportEvent:removed", on_removed)
        store.on("prices:updated", on_prices_updated)

    def _fail_pending(self, err: Exception) -> None:
        if self._pending is not None and not self._pending.future.done():
            self._pending.future.set_exception(err)


def create_client(
    *, url: str, api_key: str, reconnect: ReconnectPolicy | None = None
) -> Client:
    """Construct a realtimeodds Client.

    Call `await client.connect()` to open the WebSocket. Subscribe to events
    via `client.on(...)`. The client auto-reconnects with exponential backoff
    on transient drops; configure or disable via `reconnect`.
    """
    return Client(url=url, api_key=api_key, reconnect=reconnect)
