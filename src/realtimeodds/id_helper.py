"""Parse and compose the structured id grammar used by the wire format.

- ``SportEventId`` : ``vmid:<bookmaker>:<external_sport_event_id>``
- ``MarketId``     : ``<SportEventId>:<external_market_id>``
- ``SelectionId``  : ``<MarketId>:<external_selection_id>``

The grammar reserves ``:`` as the top-level segment separator. Producers SHOULD
avoid ``:`` inside ``external_*`` parts (use ``_`` instead). These helpers
tolerate legacy inputs where a producer embedded ``:`` internally — they always
return the longest prefix that ends before the last ``:`` segment, which is the
MarketId by definition when the input is a SelectionId.

Use the :class:`IdHelper` namespace from your application code; the module-level
functions remain available for backwards compatibility.
"""

from __future__ import annotations

from typing import cast

from ._types import Bookmaker, MarketId, SelectionId, SportEventId


def get_bookmaker(entity_id: str) -> Bookmaker:
    """Parse the bookmaker from any entity id (``vmid:<bookmaker>:...``)."""
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

    With 5+ segments we assume the input is a SelectionId and strip its
    trailing segment; with fewer it is taken verbatim (already a MarketId).
    """
    parts = entity_id.split(":")
    if len(parts) < 4:
        raise ValueError(f"Cannot extract MarketId from {entity_id!r}")
    if len(parts) < 5:
        return MarketId(entity_id)
    return MarketId(":".join(parts[:-1]))


def make_sport_event_id(bookmaker: Bookmaker, external_id: str) -> SportEventId:
    """Compose a SportEventId from its parts."""
    return SportEventId(f"vmid:{bookmaker}:{external_id}")


def make_market_id(sport_event_id: SportEventId, external_market_id: str) -> MarketId:
    """Compose a MarketId from a SportEventId and the bookmaker-specific market id."""
    return MarketId(f"{sport_event_id}:{external_market_id}")


def make_selection_id(market_id: MarketId, external_selection_id: str) -> SelectionId:
    """Compose a SelectionId from a MarketId and the bookmaker-specific selection id."""
    return SelectionId(f"{market_id}:{external_selection_id}")


class IdHelper:
    """Namespace for parsing and composing the structured entity id grammar.

    Equivalent to ``IdHelper`` in the JavaScript and Java SDKs — same method
    names (in snake_case), same semantics. Use these helpers when you need to
    derive ids from each other; avoid parsing the strings yourself.

    Example::

        from realtimeodds import IdHelper

        IdHelper.get_bookmaker(selection_id)        # 'ps3838'
        IdHelper.get_sport_event_id(market_id)      # SportEventId('vmid:ps3838:1610547234')
        IdHelper.get_market_id(selection_id)        # MarketId('vmid:ps3838:...:total_full_match_221')
    """

    get_bookmaker = staticmethod(get_bookmaker)
    get_sport_event_id = staticmethod(get_sport_event_id)
    get_market_id = staticmethod(get_market_id)
    make_sport_event_id = staticmethod(make_sport_event_id)
    make_market_id = staticmethod(make_market_id)
    make_selection_id = staticmethod(make_selection_id)

    def __init__(self) -> None:
        raise TypeError("IdHelper is a namespace; use its static methods directly.")
