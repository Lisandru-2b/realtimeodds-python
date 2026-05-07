"""OddsStore — upsert / update_prices / remove + event emission."""

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
from realtimeodds._store import (
    OddsStore,
    PricesUpdatedPayload,
    SportEventRemovedPayload,
)


def _make_event() -> BasketballMatch:
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
        selections={sel_home.id: sel_home, sel_away.id: sel_away},
        home_team="Lakers",
        away_team="Celtics",
    )
    return BasketballMatch(
        id=SportEventId("vmid:ps3838:1"),
        kind="se:basketball_match",
        competition="comp:basketball.nba",
        markets={market.id: market},
        home_team="Lakers",
        away_team="Celtics",
    )


def test_upsert_emits_is_new_then_not_new() -> None:
    store = OddsStore()
    seen: list[tuple[str, bool]] = []
    store.on(
        "sportEvent:upserted",
        lambda payload: seen.append((payload.sport_event.id, payload.is_new)),    )

    se = _make_event()
    store.upsert_sport_event(se)
    store.upsert_sport_event(se)

    assert seen == [(se.id, True), (se.id, False)]


def test_get_all_sport_events_returns_mapping() -> None:
    store = OddsStore()
    se = _make_event()
    store.upsert_sport_event(se)
    snapshot = store.get_all_sport_events()
    assert se.id in snapshot
    assert snapshot[se.id].name == "Lakers / Celtics"


def test_update_prices_replaces_quote_and_emits() -> None:
    store = OddsStore()
    se = _make_event()
    store.upsert_sport_event(se)

    captured: list[PricesUpdatedPayload] = []
    store.on("prices:updated", lambda p: captured.append(p))
    home_id = SelectionId("vmid:ps3838:1:m:home")
    ok = store.update_prices(se.id, {home_id: 2.00})
    assert ok
    assert len(captured) == 1
    assert captured[0].prices[home_id] == 2.00

    new_se = store.get_sport_event(se.id)
    assert new_se is not None
    market = next(iter(new_se.markets.values()))
    sel = market.get_selection(home_id)
    assert sel is not None
    assert sel.price == 2.00


def test_remove_sport_event_emits_and_returns_true() -> None:
    store = OddsStore()
    se = _make_event()
    store.upsert_sport_event(se)

    captured: list[SportEventRemovedPayload] = []
    store.on("sportEvent:removed", lambda p: captured.append(p))
    assert store.remove_sport_event(se.id) is True
    assert store.remove_sport_event(se.id) is False  # idempotent
    assert len(captured) == 1
    assert captured[0].sport_event_id == se.id
    assert store.size == 0


def test_clear_resets_and_emits() -> None:
    store = OddsStore()
    store.upsert_sport_event(_make_event())
    seen: list[None] = []
    store.on("store:cleared", lambda _p: seen.append(None))
    store.clear()
    assert store.size == 0
    assert len(seen) == 1
