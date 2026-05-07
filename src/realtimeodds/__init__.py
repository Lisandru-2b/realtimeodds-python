"""realtimeodds — Real-time betting odds SDK for Python.

Multi-bookmaker, sport-discriminated, asyncio-first. Wraps the `sb-orchestrator`
gateway WebSocket and exposes spec-compliant events to consumers.

Quickstart:
    >>> import asyncio
    >>> from realtimeodds import create_client
    >>>
    >>> async def main() -> None:
    ...     client = create_client(url="wss://api.realtimeodds.xyz", api_key="...")
    ...     client.on("sportEvent:added", lambda ev: print(ev.sport_event.id))
    ...     await client.connect()
    ...     await asyncio.sleep(60)
    ...     await client.disconnect()
    >>>
    >>> asyncio.run(main())
"""

from ._entities import (
    BasketballHandicap,
    BasketballMatch,
    BasketballMoneyline,
    BasketballPlayerPropOverUnder,
    BasketballTotal,
    FootballMatch,
    FootballMoneyline,
    Level,
    Market,
    OrderBook,
    Quote,
    Selection,
    SportEvent,
    TennisMatch,
    TennisMoneyline,
)
from ._gateway import ReconnectPolicy
from ._types import (
    BasketballPeriod,
    BasketballTotalScope,
    Bookmaker,
    Competition,
    MarketId,
    MarketKind,
    PlayerPropType,
    SelectionId,
    SelectionKind,
    SelectionResult,
    Sport,
    SportEventId,
    SportEventKind,
)
from .client import (
    Client,
    ConnectionState,
    ConnectionStatus,
    DisconnectedEvent,
    ErrorEvent,
    OddsChangedEvent,
    ReconnectingEvent,
    Snapshot,
    SportEventAddedEvent,
    SportEventRemovedEvent,
    SportEventUpdatedEvent,
    create_client,
)

__version__ = "0.1.0"

__all__ = [
    # Client surface
    "Client",
    "ConnectionState",
    "ConnectionStatus",
    "DisconnectedEvent",
    "ErrorEvent",
    "OddsChangedEvent",
    "ReconnectPolicy",
    "ReconnectingEvent",
    "Snapshot",
    "SportEventAddedEvent",
    "SportEventRemovedEvent",
    "SportEventUpdatedEvent",
    "create_client",
    # Entities
    "BasketballHandicap",
    "BasketballMatch",
    "BasketballMoneyline",
    "BasketballPlayerPropOverUnder",
    "BasketballTotal",
    "FootballMatch",
    "FootballMoneyline",
    "Level",
    "Market",
    "OrderBook",
    "Quote",
    "Selection",
    "SportEvent",
    "TennisMatch",
    "TennisMoneyline",
    # Type aliases
    "BasketballPeriod",
    "BasketballTotalScope",
    "Bookmaker",
    "Competition",
    "MarketId",
    "MarketKind",
    "PlayerPropType",
    "SelectionId",
    "SelectionKind",
    "SelectionResult",
    "Sport",
    "SportEventId",
    "SportEventKind",
    # Version
    "__version__",
]
