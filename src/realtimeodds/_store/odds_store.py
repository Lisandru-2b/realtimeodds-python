"""OddsStore — in-memory replica of sb-odds-store/OddsStore.

Holds the latest known SportEvent per id. Mutations re-create the SportEvent
through its internal `_with_*` chain so consumers tracking by reference can
swap their pointer atomically.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .._emitter import TypedEmitter
from .._entities import Market, Selection, SportEvent
from .._types import MarketId, SelectionId, SportEventId, SportEventKind
from .events import (
    PricesUpdatedPayload,
    SportEventRemovedPayload,
    SportEventUpsertedPayload,
)


class OddsStore:
    """Mutable container for SportEvent instances. Emits change events."""

    __slots__ = ("_by_kind", "_emitter", "_sport_events")

    def __init__(self) -> None:
        self._emitter = TypedEmitter()
        self._sport_events: dict[SportEventId, SportEvent] = {}
        self._by_kind: dict[str, dict[SportEventId, SportEvent]] = {}

    # ─── Events ─────────────────────────────────────────────────────────────

    def on(self, event: str, listener: object) -> None:
        self._emitter.on(event, listener)  # type: ignore[arg-type]

    def off(self, event: str, listener: object) -> None:
        self._emitter.off(event, listener)  # type: ignore[arg-type]

    # ─── Mutations ──────────────────────────────────────────────────────────

    def upsert_sport_event(self, sport_event: SportEvent) -> None:
        is_new = sport_event.id not in self._sport_events
        self._sport_events[sport_event.id] = sport_event
        self._by_kind.setdefault(sport_event.kind, {})[sport_event.id] = sport_event
        self._emitter.emit(
            "sportEvent:upserted",
            SportEventUpsertedPayload(sport_event=sport_event, is_new=is_new),
        )

    def update_prices(
        self, sport_event_id: SportEventId, prices: Mapping[SelectionId, float]
    ) -> bool:
        existing = self._sport_events.get(sport_event_id)
        if existing is None:
            return False
        try:
            updated = existing._with_updated_prices(prices)
        except Exception:
            return False
        self._sport_events[sport_event_id] = updated
        self._by_kind.setdefault(updated.kind, {})[updated.id] = updated
        self._emitter.emit(
            "prices:updated",
            PricesUpdatedPayload(sport_event_id=sport_event_id, prices=prices),
        )
        return True

    def remove_sport_event(self, sport_event_id: SportEventId) -> bool:
        existing = self._sport_events.pop(sport_event_id, None)
        if existing is None:
            return False
        kind_map = self._by_kind.get(existing.kind)
        if kind_map is not None:
            kind_map.pop(sport_event_id, None)
        self._emitter.emit(
            "sportEvent:removed",
            SportEventRemovedPayload(sport_event_id=sport_event_id),
        )
        return True

    def clear(self) -> None:
        self._sport_events.clear()
        self._by_kind.clear()
        self._emitter.emit("store:cleared", None)

    def replace_with_snapshot(self, events: list[SportEvent]) -> None:
        """Atomically replace the store's contents with the given list of sport
        events. Used by `resync` handling — the previous view is discarded
        before the new one is inserted, and no per-event upsert/remove signals
        are emitted (callers consuming the resync event do their own rebuild).
        """
        self._sport_events.clear()
        self._by_kind.clear()
        for ev in events:
            self._sport_events[ev.id] = ev
            self._by_kind.setdefault(ev.kind, {})[ev.id] = ev

    # ─── Queries ────────────────────────────────────────────────────────────

    def get_sport_event(self, sport_event_id: SportEventId) -> SportEvent | None:
        return self._sport_events.get(sport_event_id)

    def get_market(self, market_id: MarketId | SelectionId | str) -> Market | None:
        for sport_event in self._sport_events.values():
            market = sport_event.get_market(market_id)
            if market is not None:
                return market
        return None

    def get_selection(self, selection_id: SelectionId) -> Selection | None:
        for sport_event in self._sport_events.values():
            selection = sport_event.get_selection(selection_id)
            if selection is not None:
                return selection
        return None

    def get_all_sport_events(self) -> Mapping[SportEventId, SportEvent]:
        return MappingProxyType(self._sport_events)

    def get_sport_events_by_kind(self, kind: SportEventKind | str) -> Mapping[SportEventId, SportEvent]:
        return MappingProxyType(self._by_kind.get(kind, {}))

    @property
    def size(self) -> int:
        return len(self._sport_events)
