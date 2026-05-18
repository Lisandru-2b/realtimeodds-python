"""Parse the structured id grammar used by the wire format.

- SportEventId : `vmid:<bookmaker>:<external_sport_event_id>`
- MarketId     : `<SportEventId>:<external_market_id>`
- SelectionId  : `<MarketId>:<external_selection_id>`
"""

from __future__ import annotations

from typing import cast

from ._types import Bookmaker, MarketId, SelectionId, SportEventId


def get_bookmaker(entity_id: str) -> Bookmaker:
    """Parse the bookmaker from any entity id (`vmid:<bookmaker>:...`)."""
    parts = entity_id.split(":")
    if len(parts) < 3 or parts[0] != "vmid":
        raise ValueError(f"Invalid entity id format: {entity_id!r}")
    return cast(Bookmaker, parts[1])


def get_sport_event_id(entity_id: str) -> SportEventId:
    """Truncate any entity id to the SportEventId prefix."""
    parts = entity_id.split(":")
    if len(parts) < 3:
        raise ValueError(f"Invalid entity id format: {entity_id!r}")
    return SportEventId(":".join(parts[:3]))


def get_market_id(entity_id: str) -> MarketId:
    """Resolve any MarketId or SelectionId to the MarketId.

    The grammar reserves `:` as the top-level segment separator. Producers
    SHOULD avoid `:` inside `external_market_id` / `external_selection_id`
    (use `_` instead). This helper tolerates inputs where a producer still
    embedded `:` internally: with 5+ segments we assume the input is a
    SelectionId and strip its trailing segment; with fewer it is taken
    verbatim (already a MarketId).
    """
    parts = entity_id.split(":")
    if len(parts) < 4:
        raise ValueError(f"Cannot extract MarketId from {entity_id!r}")
    if len(parts) < 5:
        return MarketId(entity_id)
    return MarketId(":".join(parts[:-1]))


def make_sport_event_id(bookmaker: Bookmaker, external_id: str) -> SportEventId:
    return SportEventId(f"vmid:{bookmaker}:{external_id}")


def make_market_id(sport_event_id: SportEventId, external_market_id: str) -> MarketId:
    return MarketId(f"{sport_event_id}:{external_market_id}")


def make_selection_id(market_id: MarketId, external_selection_id: str) -> SelectionId:
    return SelectionId(f"{market_id}:{external_selection_id}")
