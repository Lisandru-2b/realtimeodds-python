"""OrderBook — limit order book for a CLOB selection (e.g. Polymarket)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Level:
    """A single price level."""

    price: float
    size: float


@dataclass(frozen=True, slots=True)
class OrderBook:
    """Limit order book at a point in time.

    `bids` are sorted DESC by price (best first). `asks` are sorted ASC by price
    (best first). `timestamp` is in milliseconds since epoch.
    """

    bids: tuple[Level, ...]
    asks: tuple[Level, ...]
    timestamp: int

    @property
    def best_bid(self) -> Level | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Level | None:
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_ask is None or self.best_bid is None:
            return None
        return self.best_ask.price - self.best_bid.price

    @property
    def mid_price(self) -> float | None:
        if self.best_ask is None or self.best_bid is None:
            return None
        return (self.best_ask.price + self.best_bid.price) / 2.0

    def available_size_up_to(self, max_price: float) -> float:
        """Total ask-side size available up to (and including) `max_price`."""
        total = 0.0
        for level in self.asks:
            if level.price > max_price:
                break
            total += level.size
        return total

    @classmethod
    def _from_json(cls, data: dict[str, Any]) -> OrderBook:
        bids = tuple(
            Level(price=float(b["price"]), size=float(b["size"])) for b in data.get("bids", [])
        )
        asks = tuple(
            Level(price=float(a["price"]), size=float(a["size"])) for a in data.get("asks", [])
        )
        return cls(bids=bids, asks=asks, timestamp=int(data["timestamp"]))
