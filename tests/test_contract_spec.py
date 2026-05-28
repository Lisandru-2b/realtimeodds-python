from __future__ import annotations

import json
from pathlib import Path

from realtimeodds import MARKET_KINDS, SPORT_EVENT_KINDS, UnknownMarket, UnknownSportEvent
from realtimeodds._entities import market_from_json, sport_event_from_json


ROOT = Path(__file__).resolve().parents[2]
COMMON = json.loads((ROOT / "realtimeodds-spec/schemas/v1/common.schema.json").read_text())["$defs"]


def _selection_kind(market_kind: str) -> str:
    sport_event_name, market_name = market_kind.removeprefix("market:").split(".")
    if market_name == "total" or market_name == "player_prop_over_under":
        return "over/under"
    if sport_event_name in {"tennis_match", "boxing_fight", "mma_fight"}:
        return "competitor1/competitor2"
    if market_name == "regulation_moneyline":
        return "home/draw/away"
    if sport_event_name in {"football_match", "handball_match", "rugby_league_match"} and market_name == "moneyline":
        return "home/draw/away"
    return "home/away"


def _results(selection_kind: str) -> list[str]:
    return {
        "over/under": ["over", "under"],
        "home/draw/away": ["home", "draw", "away"],
        "home/away": ["home", "away"],
        "competitor1/competitor2": ["competitor1", "competitor2"],
    }[selection_kind]


def _market_fixture(market_kind: str) -> dict[str, object]:
    sport_event_name, market_name = market_kind.removeprefix("market:").split(".")
    selection_kind = _selection_kind(market_kind)
    fixture: dict[str, object] = {
        "id": f"vmid:ps3838:1:{market_name}",
        "kind": market_kind,
        "selectionKind": selection_kind,
        "isSynthetic": False,
        "selections": [
            {
                "id": f"vmid:ps3838:1:{market_name}:{result}",
                "kind": selection_kind,
                "result": result,
                "quote": {"price": 2.0, "timestamp": 1},
            }
            for result in _results(selection_kind)
        ],
    }
    if sport_event_name in {"tennis_match", "boxing_fight", "mma_fight"}:
        fixture.update({"competitor1": "A", "competitor2": "B"})
    elif market_name != "player_prop_over_under":
        fixture.update({"homeTeam": "Home", "awayTeam": "Away"})
    if market_name in {"moneyline", "handicap", "total"} and sport_event_name not in {
        "boxing_fight",
        "cricket_match",
        "mma_fight",
    }:
        fixture["period"] = "full_match"
    if market_name == "handicap":
        fixture["handicap"] = -1.5
    if market_name == "total":
        fixture["scope"] = "match"
        fixture["cut"] = 2.5
    if sport_event_name == "tennis_match" and market_name in {"handicap", "total"}:
        fixture["unit"] = "games"
    if market_name == "player_prop_over_under":
        fixture.update({"playerName": "Player", "propType": "points", "cut": 20.5})
    return fixture


def _event_fixture(event_kind: str) -> dict[str, object]:
    sport_event_name = event_kind.removeprefix("se:")
    sport = sport_event_name.removesuffix("_match").removesuffix("_fight")
    fixture: dict[str, object] = {
        "id": "vmid:ps3838:1",
        "kind": event_kind,
        "competition": f"comp:{sport}.test",
        "markets": [],
    }
    if sport_event_name in {"tennis_match", "boxing_fight", "mma_fight"}:
        fixture.update({"competitor1": "A", "competitor2": "B"})
    else:
        fixture.update({"homeTeam": "Home", "awayTeam": "Away"})
    return fixture


def test_sdk_kind_constants_match_spec() -> None:
    assert list(SPORT_EVENT_KINDS) == COMMON["SportEventKind"]["enum"]
    assert list(MARKET_KINDS) == COMMON["MarketKind"]["enum"]


def test_all_spec_market_kinds_deserialize_without_unknown_fallback() -> None:
    for kind in COMMON["MarketKind"]["enum"]:
        market = market_from_json(_market_fixture(kind), strict=True)
        assert market.kind == kind
        assert not isinstance(market, UnknownMarket)


def test_all_spec_sport_event_kinds_deserialize_without_unknown_fallback() -> None:
    for kind in COMMON["SportEventKind"]["enum"]:
        event = sport_event_from_json(_event_fixture(kind), strict=True)
        assert event.kind == kind
        assert not isinstance(event, UnknownSportEvent)
