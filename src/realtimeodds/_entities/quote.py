"""Quote — a decimal-odds quote at a point in time."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Quote:
    """A decimal-odds quote.

    `timestamp` is in milliseconds since epoch — observation time, set by
    whichever party constructed the Quote (gateway, then SDK at hydration).
    Approximates freshness; not the bookmaker's authoritative emit time.
    """

    price: float
    timestamp: int
    size: float | None = None

    @property
    def implied_probability(self) -> float:
        """`1 / price`. Useful for margin calculations."""
        return 1.0 / self.price

    @classmethod
    def _create(cls, price: float, size: float | None = None) -> Quote:
        """Internal: create a Quote with the current local timestamp."""
        return cls(price=price, size=size, timestamp=int(time.time() * 1000))

    @classmethod
    def _from_json(cls, data: dict[str, Any]) -> Quote:
        return cls(
            price=float(data["price"]),
            size=float(data["size"]) if data.get("size") is not None else None,
            timestamp=int(data["timestamp"]),
        )
