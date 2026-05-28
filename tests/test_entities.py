"""Entity-level tests: validation + getters + JSON roundtrip."""

from __future__ import annotations

import pytest

from realtimeodds import (
    BasketballHandicap,
    BasketballMatch,
    BasketballMoneyline,
    Level,
    MarketId,
    OrderBook,
    Quote,
    Selection,
    SelectionId,
    SportEventId,
    UnknownMarket,
)
from realtimeodds._entities import market_from_json, sport_event_from_json


def _selections_dict(*selections: Selection) -> dict[SelectionId, Selection]:
    return {s.id: s for s in selections}

# ─── Quote ─────────────────────────────────────────────────────────────────


def test_quote_implied_probability() -> None:
    q = Quote(price=2.0, timestamp=0)
    assert q.implied_probability == 0.5

    q = Quote(price=4.0, timestamp=0)
    assert q.implied_probability == 0.25


def test_quote_size_optional() -> None:
    q = Quote(price=1.91, timestamp=1234)
    assert q.size is None

    q = Quote(price=1.91, timestamp=1234, size=1500.0)
    assert q.size == 1500.0


# ─── OrderBook ─────────────────────────────────────────────────────────────


def test_order_book_best_bid_ask_and_spread() -> None:
    book = OrderBook(
        bids=(Level(price=1.72, size=8400), Level(price=1.71, size=12000)),
        asks=(Level(price=1.74, size=5600), Level(price=1.76, size=9000)),
        timestamp=0,
    )
    assert book.best_bid == Level(price=1.72, size=8400)
    assert book.best_ask == Level(price=1.74, size=5600)
    assert book.spread == pytest.approx(0.02)
    assert book.mid_price == pytest.approx(1.73)


def test_order_book_available_size_up_to() -> None:
    book = OrderBook(
        bids=(),
        asks=(
            Level(price=1.74, size=5600),
            Level(price=1.76, size=9000),
            Level(price=1.80, size=12000),
        ),
        timestamp=0,
    )
    assert book.available_size_up_to(1.74) == 5600
    assert book.available_size_up_to(1.78) == 5600 + 9000
    assert book.available_size_up_to(1.80) == 5600 + 9000 + 12000


def test_order_book_empty() -> None:
    book = OrderBook(bids=(), asks=(), timestamp=0)
    assert book.best_bid is None
    assert book.best_ask is None
    assert book.spread is None
    assert book.mid_price is None


# ─── Selection ─────────────────────────────────────────────────────────────


def test_selection_validates_result_against_kind() -> None:
    with pytest.raises(ValueError):
        Selection(
            id=SelectionId("vmid:ps3838:1:m:bad"),
            kind="home/away",
            result="over",  # invalid for home/away
        )


def test_selection_unavailable_raises_on_price() -> None:
    sel = Selection(
        id=SelectionId("vmid:ps3838:1:m:home"),
        kind="home/away",
        result="home",
    )
    assert not sel.is_available
    with pytest.raises(RuntimeError):
        _ = sel.price


def test_selection_bookmaker_derived_from_id() -> None:
    sel = Selection(
        id=SelectionId("vmid:polymarket:0xabc:m:c1"),
        kind="competitor1/competitor2",
        result="competitor1",
    )
    assert sel.bookmaker == "polymarket"


# ─── Market ────────────────────────────────────────────────────────────────


def test_basketball_moneyline_margin_and_fair_odd() -> None:
    sel_home = Selection(
        id=SelectionId("vmid:ps3838:1:m:home"),
        kind="home/away",
        result="home",
        quote=Quote(price=1.91, timestamp=0),
    )
    sel_away = Selection(
        id=SelectionId("vmid:ps3838:1:m:away"),
        kind="home/away",
        result="away",
        quote=Quote(price=1.95, timestamp=0),
    )
    market = BasketballMoneyline(
        id=MarketId("vmid:ps3838:1:m"),
        kind="market:basketball_match.moneyline",
        selection_kind="home/away",
        is_synthetic=False,
        selections=_selections_dict(sel_home, sel_away),
        home_team="Lakers",
        away_team="Celtics",
        period="full_match",
    )
    assert market.is_fully_available
    margin = market.calculate_margin()
    assert margin > 0
    # Fair odd > raw price (margin is removed)
    assert market.get_fair_odd("home") > sel_home.price
    assert market.get_fair_odd("away") > sel_away.price


def test_basketball_handicap_selection_name() -> None:
    sel_home = Selection(
        id=SelectionId("vmid:ps3838:1:hcap:home"),
        kind="home/away",
        result="home",
        quote=Quote(price=1.91, timestamp=0),
    )
    sel_away = Selection(
        id=SelectionId("vmid:ps3838:1:hcap:away"),
        kind="home/away",
        result="away",
        quote=Quote(price=1.91, timestamp=0),
    )
    market = BasketballHandicap(
        id=MarketId("vmid:ps3838:1:hcap"),
        kind="market:basketball_match.handicap",
        selection_kind="home/away",
        is_synthetic=False,
        selections=_selections_dict(sel_home, sel_away),
        home_team="Lakers",
        away_team="Celtics",
        period="full_match",
        handicap=-3.5,
    )
    assert "Lakers -3.5" in market.get_selection_name("home")
    assert "Celtics +3.5" in market.get_selection_name("away")


def test_market_rejects_duplicate_selection_result() -> None:
    a = Selection(
        id=SelectionId("vmid:ps3838:1:m:home"),
        kind="home/away",
        result="home",
        quote=Quote(price=1.91, timestamp=0),
    )
    b = Selection(
        id=SelectionId("vmid:ps3838:1:m:home2"),  # different id, same result
        kind="home/away",
        result="home",
        quote=Quote(price=2.00, timestamp=0),
    )
    with pytest.raises(ValueError):
        BasketballMoneyline(
            id=MarketId("vmid:ps3838:1:m"),
            kind="market:basketball_match.moneyline",
            selection_kind="home/away",
            is_synthetic=False,
            selections=_selections_dict(a, b),
            home_team="X",
            away_team="Y",
        )


# ─── SportEvent ─────────────────────────────────────────────────────────────


def test_basketball_match_lookup_and_narrowing() -> None:
    se = BasketballMatch(
        id=SportEventId("vmid:ps3838:1"),
        kind="se:basketball_match",
        competition="comp:basketball.nba",
        markets={},
        home_team="Lakers",
        away_team="Celtics",
    )
    assert se.sport == "basketball"
    assert se.bookmaker == "ps3838"
    assert se.name == "Lakers / Celtics"
    assert se.get_market("vmid:ps3838:1:nope") is None


# ─── JSON deserialization (spec examples) ──────────────────────────────────


_BASKETBALL_FIXTURE: dict[str, object] = {
    "id": "vmid:ps3838:1610547234",
    "kind": "se:basketball_match",
    "competition": "comp:basketball.nba",
    "sportRegion": "USA",
    "startDate": "2026-05-05T00:00:00Z",
    "homeTeam": "Lakers",
    "awayTeam": "Celtics",
    "markets": [
        {
            "id": "vmid:ps3838:1610547234:ml",
            "kind": "market:basketball_match.moneyline",
            "selectionKind": "home/away",
            "isSynthetic": False,
            "homeTeam": "Lakers",
            "awayTeam": "Celtics",
            "period": "full_match",
            "selections": [
                {
                    "id": "vmid:ps3838:1610547234:ml:home",
                    "kind": "home/away",
                    "result": "home",
                    "quote": {"price": 1.91, "timestamp": 1714823400000, "size": 1500},
                },
                {
                    "id": "vmid:ps3838:1610547234:ml:away",
                    "kind": "home/away",
                    "result": "away",
                    "quote": {"price": 1.95, "timestamp": 1714823400000},
                },
            ],
        }
    ],
}


def test_sport_event_from_json_basketball() -> None:
    se = sport_event_from_json(_BASKETBALL_FIXTURE)
    assert isinstance(se, BasketballMatch)
    assert se.bookmaker == "ps3838"
    assert se.start_date is not None
    assert se.start_date.year == 2026
    market = next(iter(se.markets.values()))
    assert isinstance(market, BasketballMoneyline)
    assert market.is_fully_available


def test_market_from_json_unknown_kind_is_tolerated_by_default() -> None:
    market = market_from_json({"kind": "market:nonexistent", "id": "x", "selectionKind": "home/away", "isSynthetic": False, "selections": []})
    assert isinstance(market, UnknownMarket)
    assert market.kind == "market:nonexistent"


def test_market_from_json_unknown_kind_raises_in_strict_mode() -> None:
    with pytest.raises(ValueError):
        market_from_json({"kind": "market:nonexistent", "id": "x", "selectionKind": "home/away", "isSynthetic": False, "selections": []}, strict=True)
