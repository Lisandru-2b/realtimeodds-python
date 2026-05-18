# realtimeodds

Real-time betting odds SDK for Python — multi-bookmaker, sport-discriminated, asyncio-first.

The SDK is a **strict replica** of the gateway's internal stores: same shapes, same fields, same getters and read-side methods (transposed to Pythonic `snake_case`). Only the mutation surface (`_with_*`) is intentionally underscore-prefixed.

> Status: 0.3.0 — alpha. The shapes documented here are intended to remain stable through the 0.x line.

## Install

```bash
pip install realtimeodds
```

Requires Python 3.10+.

## Quickstart

```python
import asyncio
from realtimeodds import create_client


async def main() -> None:
    client = create_client(
        url="wss://api.realtimeodds.xyz",
        api_key="your-api-key",
    )

    def on_odds(ev):
        ctx = client.odds.find_context(ev.selection_id)
        if ctx is None or ctx.sport_event.kind != "se:basketball_match":
            return
        print(
            f"[{ev.bookmaker}] {ctx.sport_event.name} · "
            f"{ctx.market.kind} · {ctx.selection.result} → {ev.quote.price}"
        )

    client.on("odds:changed", on_odds)

    await client.connect()
    try:
        await asyncio.sleep(60)
    finally:
        await client.disconnect()


asyncio.run(main())
```

## API

| API | Behaviour |
|---|---|
| `create_client(url, api_key, reconnect=None)` | Construct a client. |
| `await client.connect()` | Open the WebSocket. Resolves on first successful connection; raises on invalid api_key, incompatible protocol, or exhausted reconnect attempts. Concurrent calls return the same future. |
| `await client.disconnect()` | Close and stop reconnecting. Idempotent. Raises any in-flight `connect()`. The live `OddsBook` is emptied immediately. |
| `client.odds` | Live `OddsBook` — same instance every read, mutated in place as wire messages arrive. |
| `client.snapshot()` | Frozen clone of the live book taken at the moment of the call. Use when you need a stable view across multiple reads. |
| `client.get_sport_event(id)` | O(1) single lookup. Returns `None` if unknown. Convenience shortcut for `client.odds.get_sport_event(id)`. |
| `client.on(event, cb)` / `client.off(event, cb)` | Subscribe / unsubscribe. Synchronous callbacks. |
| `client.connection_state` | `ConnectionState(status, last_error)`. Use lifecycle events for reactive flows. |

### `OddsBook`

Read-only view of every sport event the SDK knows about, across every bookmaker. All lookups are O(1) thanks to maintained inverse indexes.

```python
client.odds.size                              # number of sport events
client.odds.get_sport_event(sport_event_id)   # SportEvent | None
client.odds.get_market(market_id)             # Market | None
client.odds.get_selection(selection_id)       # Selection | None
client.odds.find_context(selection_id)        # OddsContext | None
list(client.odds)                             # iterate every event
```

`find_context` returns an `OddsContext(sport_event, market, selection)` in one O(1) lookup — recommended inside an `odds:changed` handler when you need more than just the price.

### Events

Synchronous callbacks. Each event payload is a frozen dataclass.

| Event | Payload |
|---|---|
| `connected` | `None` |
| `disconnected` | `DisconnectedEvent(will_reconnect, code, reason)` — the live `OddsBook` is emptied before this fires. |
| `reconnecting` | `ReconnectingEvent(attempt, delay_ms)` |
| `error` | `ErrorEvent(message, fatal)` |
| `sportEvent:added` | `SportEventAddedEvent(sport_event, received_at)` |
| `sportEvent:updated` | `SportEventUpdatedEvent(sport_event, received_at)` — fires on metadata change OR on any odds change |
| `sportEvent:removed` | `SportEventRemovedEvent(bookmaker, sport_event_id, received_at)` |
| `odds:changed` | `OddsChangedEvent(bookmaker, sport_event_id, market_id, selection_id, quote, received_at)` |
| `source:cleared` | `SourceClearedEvent(bookmaker, received_at)` — an entire bookmaker source went away. The SDK has already purged its events from the live book before this fires. |
| `resync` | `ResyncEvent(bookmaker, reason, sport_events, received_at)` — atomic full-state replacement for one bookmaker. The live book has already swapped the affected slice before this fires. |

Close codes 4001/4002/4003 are fatal auth close codes; `fatal=True` errors stop the client.

## Entities

The SDK exposes the same shapes the gateway holds, transposed to Pythonic naming. All entities are frozen dataclasses with computed properties.

- **`SportEvent`** (`BasketballMatch | FootballMatch | TennisMatch`): `id`, `kind`, `bookmaker`, `sport`, `competition`, `sport_region`, `start_date` (Python `datetime`), `match_url`, `name`, `markets: Mapping`, plus `get_market(id)`, `get_selection(id)`.
- **`Market`** (6 variants discriminated by `kind`): `id`, `kind`, `selection_kind`, `is_synthetic`, `bookmaker`, `market_name`, `sport_event_name`, `sport`, `category`, `is_available`, `is_fully_available`, `number_of_possible_results`, `selections: Mapping`, plus `get_selection(id)`, `get_selection_by_result(result)`, `get_fair_odd(result)`, `calculate_margin()`, etc.
- **`Selection`**: `id`, `kind`, `result`, `quote`, `order_book`, `bookmaker`, `is_available`, `price` (raises if unavailable).
- **`Quote`**: `price`, `size`, `timestamp`, `implied_probability`.
- **`OrderBook`**: `bids`, `asks`, `timestamp`, `best_bid`, `best_ask`, `spread`, `mid_price`, `available_size_up_to(max_price)`.

Sport-specific fields (`home_team`/`away_team`/`competitor1`/`competitor2`/`period`/`handicap`/`scope`/`cut`/`player_name`/`prop_type`) live on the relevant subtypes. Branch on `kind` (or use `isinstance`) to access them with type narrowing.

## Sport / kind narrowing

```python
def on_added(ev):
    se = ev.sport_event
    if se.sport == "basketball":
        # mypy / IDE narrows to BasketballMatch
        print(se.home_team, se.away_team)
    elif se.sport == "tennis":
        print(se.competitor1, se.competitor2)

    for market in se.markets.values():
        if market.kind == "market:basketball_match.handicap":
            print(market.handicap)
```

## Multi-bookmaker behaviour

Every `SportEvent` carries a `bookmaker` property (derived from its `id`). The same underlying match (e.g. *Lakers vs Celtics*) reported by two bookmakers is **two distinct entries** with different `id` and `bookmaker`. Filter to one bookmaker:

```python
ps3838_events = [
    ev for ev in client.odds
    if ev.bookmaker == "ps3838"
]
```

## Reconnect tuning

Default policy: exponential backoff `1s → 30s`, factor 2, ±30% jitter, unbounded attempts. Override per client:

```python
from realtimeodds import create_client, ReconnectPolicy

client = create_client(
    url="wss://api.realtimeodds.xyz",
    api_key="...",
    reconnect=ReconnectPolicy(
        initial_delay_ms=500,
        max_delay_ms=10_000,
        max_attempts=20,
    ),
)


def on_error(ev):
    if ev.fatal:
        print(f"giving up: {ev.message}")


client.on("error", on_error)
```

## Time semantics

- `received_at` (on every event payload) — local clock when the SDK received the message. Authoritative for SDK-side latency analysis.
- `quote.timestamp` / `order_book.timestamp` — observation time set by whichever party constructed the object (gateway or SDK at hydration). Approximates freshness; not the bookmaker's authoritative emit time.

## Stability

This is `0.3.0`. The shapes documented above are intended to remain stable through the `0.x` line. Breaking changes will require a `0.x → 0.(x+1)` minor bump. Pre-1.0 means we may still iterate on edge-case behaviour and undocumented internals.

See [`realtimeodds-spec`](https://github.com/Lisandru-2b/realtimeodds-spec) for the wire-format JSON Schemas (used by cross-language ports for protocol-level validation).

## License

MIT — see [LICENSE](./LICENSE).
