"""Selection — a bettable outcome within a market."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .._id_helper import get_bookmaker
from .._types import (
    SELECTION_RESULT_ASSOCIATIONS,
    Bookmaker,
    SelectionId,
    SelectionKind,
    SelectionResult,
)
from .order_book import OrderBook
from .quote import Quote


@dataclass(frozen=True, slots=True)
class Selection:
    """A bettable outcome within a market.

    A selection is **unavailable** when `quote is None`. Reading `.price` on
    an unavailable selection raises `RuntimeError` (mirroring the JS port).
    """

    id: SelectionId
    kind: SelectionKind
    result: SelectionResult
    quote: Quote | None = None
    order_book: OrderBook | None = None

    def __post_init__(self) -> None:
        valid_results = SELECTION_RESULT_ASSOCIATIONS.get(self.kind)
        if valid_results is None or self.result not in valid_results:
            raise ValueError(
                f"Invalid selection result {self.result!r} for kind {self.kind!r}"
            )

    @property
    def bookmaker(self) -> Bookmaker:
        return get_bookmaker(self.id)

    @property
    def is_available(self) -> bool:
        return self.quote is not None

    @property
    def price(self) -> float:
        if self.quote is None:
            raise RuntimeError(f"Selection {self.id} is not available")
        return self.quote.price

    # ─── internal mutators (return new instance) ────────────────────────────

    def _with_quote(self, new_quote: Quote) -> Selection:
        return replace(self, quote=new_quote)

    def _with_order_book(self, new_book: OrderBook) -> Selection:
        # Mirror JS Selection.withOrderBook: derive top-of-book quote from best ask.
        quote: Quote | None
        if new_book.best_ask is not None:
            quote = Quote._create(new_book.best_ask.price, new_book.best_ask.size)
        else:
            quote = self.quote
        return replace(self, quote=quote, order_book=new_book)

    def _with_price(self, price: float, size: float | None = None) -> Selection:
        return replace(self, quote=Quote._create(price, size))

    def _with_unavailability(self) -> Selection:
        return replace(self, quote=None, order_book=None)

    @classmethod
    def _from_json(cls, data: dict[str, Any]) -> Selection:
        return cls(
            id=SelectionId(str(data["id"])),
            kind=data["kind"],
            result=data["result"],
            quote=Quote._from_json(data["quote"]) if data.get("quote") is not None else None,
            order_book=OrderBook._from_json(data["orderBook"])
            if data.get("orderBook") is not None
            else None,
        )

    @staticmethod
    def number_of_results(kind: SelectionKind) -> int:
        return len(SELECTION_RESULT_ASSOCIATIONS[kind])
