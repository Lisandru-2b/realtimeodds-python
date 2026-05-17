"""OddsBook — lookups, indexes, clone, clear_bookmaker."""

from __future__ import annotations

from realtimeodds import (
    BasketballMatch,
    BasketballMoneyline,
    MarketId,
    Quote,
    Selection,
    SelectionId,
    SportEventId,
)
from realtimeodds._book import OddsBookImpl


def _make_event(
    sport_event_id: str = "vmid:ps3838:1",
    home: str = "Lakers",
    away: str = "Celtics",
) -> BasketballMatch:
    sel_home = Selection(
        id=SelectionId(f"{sport_event_id}:m:home"),
        kind="home/away",
        result="home",
        quote=Quote(price=1.91, timestamp=0),
    )
    sel_away = Selection(
        id=SelectionId(f"{sport_event_id}:m:away"),
        kind="home/away",
        result="away",
        quote=Quote(price=1.95, timestamp=0),
    )
    market = BasketballMoneyline(
        id=MarketId(f"{sport_event_id}:m"),
        kind="market:basketball_match.moneyline",
        selection_kind="home/away",
        is_synthetic=False,
        selections={sel_home.id: sel_home, sel_away.id: sel_away},
        home_team=home,
        away_team=away,
    )
    return BasketballMatch(
        id=SportEventId(sport_event_id),
        kind="se:basketball_match",
        competition="comp:basketball.nba",
        markets={market.id: market},
        home_team=home,
        away_team=away,
    )


def test_upsert_indexes_markets_and_selections() -> None:
    book = OddsBookImpl()
    ev = _make_event()
    book.upsert(ev)

    assert book.size == 1
    assert book.get_sport_event(ev.id) is ev
    assert book.get_market(MarketId("vmid:ps3838:1:m")) is not None
    assert book.get_selection(SelectionId("vmid:ps3838:1:m:home")) is not None
    assert book.get_selection(SelectionId("vmid:ps3838:1:m:away")) is not None


def test_find_context_returns_full_hierarchy() -> None:
    book = OddsBookImpl()
    book.upsert(_make_event())

    ctx = book.find_context(SelectionId("vmid:ps3838:1:m:home"))
    assert ctx is not None
    assert ctx.sport_event.id == "vmid:ps3838:1"
    assert ctx.market.id == "vmid:ps3838:1:m"
    assert ctx.selection.id == "vmid:ps3838:1:m:home"
    assert ctx.selection.quote is not None and ctx.selection.quote.price == 1.91

    assert book.find_context(SelectionId("vmid:unknown:1:m:nope")) is None


def test_lookups_return_none_for_unknown_ids() -> None:
    book = OddsBookImpl()
    book.upsert(_make_event())
    assert book.get_sport_event(SportEventId("vmid:unknown:9")) is None
    assert book.get_market(MarketId("vmid:unknown:9:m")) is None
    assert book.get_selection(SelectionId("vmid:unknown:9:m:home")) is None


def test_remove_drops_indexes() -> None:
    book = OddsBookImpl()
    ev = _make_event()
    book.upsert(ev)
    book.remove(ev.id)

    assert book.size == 0
    assert book.get_sport_event(ev.id) is None
    assert book.get_market(MarketId("vmid:ps3838:1:m")) is None
    assert book.get_selection(SelectionId("vmid:ps3838:1:m:home")) is None


def test_clear_bookmaker_drops_only_target_bookmaker() -> None:
    book = OddsBookImpl()
    ev1 = _make_event("vmid:ps3838:1", "Lakers", "Celtics")
    ev2 = _make_event("vmid:ps3838:2", "Bulls", "Heat")
    ev3 = _make_event("vmid:polymarket:3", "Warriors", "Suns")
    book.upsert(ev1)
    book.upsert(ev2)
    book.upsert(ev3)

    removed = book.clear_bookmaker("ps3838")
    assert removed == 2
    assert book.size == 1
    assert book.get_sport_event(ev3.id) is not None
    assert book.get_sport_event(ev1.id) is None
    assert book.get_sport_event(ev2.id) is None


def test_clear_bookmaker_unknown_returns_zero() -> None:
    book = OddsBookImpl()
    book.upsert(_make_event())
    assert book.clear_bookmaker("winamax") == 0
    assert book.size == 1


def test_replace_bookmaker_swaps_slice() -> None:
    book = OddsBookImpl()
    book.upsert(_make_event("vmid:ps3838:1"))
    book.upsert(_make_event("vmid:ps3838:2"))
    book.upsert(_make_event("vmid:polymarket:3"))

    new_ev = _make_event("vmid:ps3838:9", "Knicks", "Nets")
    book.replace_bookmaker("ps3838", (new_ev,))

    assert book.size == 2
    assert book.get_sport_event(SportEventId("vmid:ps3838:1")) is None
    assert book.get_sport_event(SportEventId("vmid:ps3838:2")) is None
    assert book.get_sport_event(SportEventId("vmid:ps3838:9")) is new_ev
    assert book.get_sport_event(SportEventId("vmid:polymarket:3")) is not None


def test_clone_is_independent() -> None:
    book = OddsBookImpl()
    book.upsert(_make_event("vmid:ps3838:1"))

    frozen = book.clone()
    assert frozen.size == 1

    # Mutate the original; the clone should be unaffected.
    book.upsert(_make_event("vmid:ps3838:2"))
    book.remove(SportEventId("vmid:ps3838:1"))

    assert book.size == 1
    assert frozen.size == 1
    assert frozen.get_sport_event(SportEventId("vmid:ps3838:1")) is not None


def test_iteration_and_len() -> None:
    book = OddsBookImpl()
    book.upsert(_make_event("vmid:ps3838:1"))
    book.upsert(_make_event("vmid:ps3838:2"))

    assert len(book) == 2
    ids = sorted(ev.id for ev in book)
    assert ids == ["vmid:ps3838:1", "vmid:ps3838:2"]

    materialized = book.sport_events()
    assert len(materialized) == 2
