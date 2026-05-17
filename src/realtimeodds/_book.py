"""OddsBook — read-only view of every sport event the SDK currently knows about.

Mirror of the JS port `realtimeodds/odds_book.ts`. Two access patterns from the
public `Client`:

- ``client.odds`` returns the **live** instance, mutated in place as wire
  messages arrive. Indexes are maintained eagerly so every lookup is O(1).
- ``client.snapshot()`` returns a **frozen clone** of the live book — useful
  when you need a stable view across multiple reads.

The book is shallow: it holds references to immutable `SportEvent` instances.
A snapshot only clones the index maps, not the entities themselves.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ._entities import Market, Selection, SportEvent
from ._types import Bookmaker, MarketId, SelectionId, SportEventId


@dataclass(frozen=True, slots=True)
class OddsContext:
    """The full hierarchical context of a selection (event → market → selection)."""

    sport_event: SportEvent
    market: Market
    selection: Selection


@runtime_checkable
class OddsBook(Protocol):
    """Read-only protocol for the live and snapshot views.

    Use ``client.odds`` for the live view, ``client.snapshot()`` for a frozen
    clone. Both implement this protocol with identical semantics — they
    differ only in whether they mutate over time.
    """

    @property
    def size(self) -> int:
        """Number of sport events currently tracked, across all bookmakers."""
        ...

    def get_sport_event(self, sport_event_id: SportEventId) -> SportEvent | None:
        """Look up a single sport event by id. Returns ``None`` if unknown."""
        ...

    def get_market(self, market_id: MarketId) -> Market | None:
        """Look up a market by its global id. Returns ``None`` if no sport event
        holds a market with this id."""
        ...

    def get_selection(self, selection_id: SelectionId) -> Selection | None:
        """Look up a selection by its global id. Returns ``None`` if no market
        holds a selection with this id."""
        ...

    def find_context(self, selection_id: SelectionId) -> OddsContext | None:
        """Resolve a selection to its full hierarchical context in one O(1)
        lookup. Recommended inside an ``odds:changed`` handler."""
        ...

    def sport_events(self) -> tuple[SportEvent, ...]:
        """Materialize every sport event into a tuple. Cheap snapshot of
        references — no entity is cloned."""
        ...

    def __iter__(self) -> Iterator[SportEvent]:
        ...

    def __len__(self) -> int:
        ...


class OddsBookImpl:
    """Mutable implementation of :class:`OddsBook`.

    Not part of the public surface — only the read-only protocol escapes. The
    public `Client` owns one live instance and clones it on each ``snapshot()``.
    """

    __slots__ = ("_by_bookmaker", "_events", "_market_parent", "_selection_parent")

    def __init__(self) -> None:
        self._events: dict[SportEventId, SportEvent] = {}
        self._market_parent: dict[MarketId, SportEventId] = {}
        self._selection_parent: dict[SelectionId, MarketId] = {}
        self._by_bookmaker: dict[Bookmaker, set[SportEventId]] = {}

    # ─── Read surface ───────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._events)

    def get_sport_event(self, sport_event_id: SportEventId) -> SportEvent | None:
        return self._events.get(sport_event_id)

    def get_market(self, market_id: MarketId) -> Market | None:
        sport_event_id = self._market_parent.get(market_id)
        if sport_event_id is None:
            return None
        ev = self._events.get(sport_event_id)
        return ev.markets.get(market_id) if ev is not None else None

    def get_selection(self, selection_id: SelectionId) -> Selection | None:
        market_id = self._selection_parent.get(selection_id)
        if market_id is None:
            return None
        market = self.get_market(market_id)
        return market.get_selection(selection_id) if market is not None else None

    def find_context(self, selection_id: SelectionId) -> OddsContext | None:
        market_id = self._selection_parent.get(selection_id)
        if market_id is None:
            return None
        sport_event_id = self._market_parent.get(market_id)
        if sport_event_id is None:
            return None
        sport_event = self._events.get(sport_event_id)
        if sport_event is None:
            return None
        market = sport_event.markets.get(market_id)
        if market is None:
            return None
        selection = market.get_selection(selection_id)
        if selection is None:
            return None
        return OddsContext(sport_event=sport_event, market=market, selection=selection)

    def sport_events(self) -> tuple[SportEvent, ...]:
        return tuple(self._events.values())

    def __iter__(self) -> Iterator[SportEvent]:
        return iter(self._events.values())

    def __len__(self) -> int:
        return len(self._events)

    # ─── Mutation surface (not part of the public protocol) ─────────────────

    def upsert(self, sport_event: SportEvent) -> None:
        """Insert or replace a sport event, re-indexing its markets and selections."""
        sport_event_id = sport_event.id
        previous = self._events.get(sport_event_id)
        if previous is not None:
            self._drop_indexes(previous)
        self._events[sport_event_id] = sport_event
        self._add_indexes(sport_event)

    def remove(self, sport_event_id: SportEventId) -> None:
        """Remove a sport event by id, dropping all its indexes."""
        previous = self._events.pop(sport_event_id, None)
        if previous is None:
            return
        self._drop_indexes(previous)

    def clear_bookmaker(self, bookmaker: Bookmaker) -> int:
        """Drop every sport event belonging to ``bookmaker``. Returns the count
        of removed events — callers can use it to decide whether to emit a
        ``source:cleared`` public event.
        """
        ids = self._by_bookmaker.get(bookmaker)
        if not ids:
            return 0
        # Materialize before iterating: _drop_indexes mutates the same set,
        # which would otherwise corrupt the loop and zero out the count.
        ids_to_drop = tuple(ids)
        for sport_event_id in ids_to_drop:
            ev = self._events.pop(sport_event_id, None)
            if ev is not None:
                self._drop_indexes(ev)
        # Safety net: _drop_indexes deletes the bookmaker key when the set
        # hits 0, but make sure it's gone even on partial cleanup.
        self._by_bookmaker.pop(bookmaker, None)
        return len(ids_to_drop)

    def replace_bookmaker(
        self, bookmaker: Bookmaker, next_events: tuple[SportEvent, ...]
    ) -> None:
        """Atomically replace every sport event of ``bookmaker`` with the new
        ground truth. Used by ``resync`` handling — the previous view for that
        bookmaker is discarded before the new one is inserted.
        """
        self.clear_bookmaker(bookmaker)
        for ev in next_events:
            self.upsert(ev)

    def clear(self) -> None:
        """Drop every sport event, from every bookmaker."""
        self._events.clear()
        self._market_parent.clear()
        self._selection_parent.clear()
        self._by_bookmaker.clear()

    def clone(self) -> OddsBookImpl:
        """Shallow clone — independent maps sharing the same entity references."""
        c = OddsBookImpl()
        c._events = dict(self._events)
        c._market_parent = dict(self._market_parent)
        c._selection_parent = dict(self._selection_parent)
        c._by_bookmaker = {k: set(v) for k, v in self._by_bookmaker.items()}
        return c

    # ─── Private indexing helpers ───────────────────────────────────────────

    def _add_indexes(self, sport_event: SportEvent) -> None:
        sport_event_id = sport_event.id
        bookmaker = sport_event.bookmaker
        self._by_bookmaker.setdefault(bookmaker, set()).add(sport_event_id)
        for market_id, market in sport_event.markets.items():
            self._market_parent[market_id] = sport_event_id
            for selection_id in market.selections:
                self._selection_parent[selection_id] = market_id

    def _drop_indexes(self, sport_event: SportEvent) -> None:
        sport_event_id = sport_event.id
        bookmaker = sport_event.bookmaker
        ids = self._by_bookmaker.get(bookmaker)
        if ids is not None:
            ids.discard(sport_event_id)
            if not ids:
                self._by_bookmaker.pop(bookmaker, None)
        for market_id, market in sport_event.markets.items():
            self._market_parent.pop(market_id, None)
            for selection_id in market.selections:
                self._selection_parent.pop(selection_id, None)
