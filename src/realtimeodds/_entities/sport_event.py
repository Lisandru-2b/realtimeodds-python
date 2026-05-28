"""Sport event entities and JSON deserialization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import MappingProxyType
from typing import Any, cast

from .._types import (
    SPORT_OF_SPORT_EVENT_NAMES,
    Bookmaker,
    MarketId,
    SelectionId,
    Sport,
    SportEventId,
)
from ..id_helper import get_bookmaker, get_market_id
from .market import Market, market_from_json
from .selection import Selection


def _wrap_markets(markets: Mapping[MarketId, Market] | Iterable[Market]) -> Mapping[MarketId, Market]:
    if isinstance(markets, Mapping):
        d = dict(markets)
    else:
        d = {m.id: m for m in markets}
    return MappingProxyType(d)


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(data or {}))


@dataclass(frozen=True, slots=True, kw_only=True)
class SportEvent:
    id: SportEventId
    kind: str
    competition: str
    markets: Mapping[MarketId, Market] = field(default_factory=dict)
    sport_region: str | None = None
    start_date: datetime | None = None
    match_url: str | None = None

    def __post_init__(self) -> None:
        wrapped = _wrap_markets(self.markets)
        object.__setattr__(self, "markets", wrapped)

        for market in self.markets.values():
            if market.sport_event_name != self.sport_event_name and market.sport_event_name != "unknown":
                raise ValueError(
                    f"Market kind {market.kind!r} is not compatible with sport event kind {self.kind!r}"
                )

    @property
    def bookmaker(self) -> Bookmaker:
        return get_bookmaker(self.id)

    @property
    def sport_event_name(self) -> str:
        return self.kind.split(":")[1] if ":" in self.kind else "unknown"

    @property
    def sport(self) -> Sport:
        return SPORT_OF_SPORT_EVENT_NAMES[self.sport_event_name]

    @property
    def name(self) -> str:
        return self.id

    def get_market(self, entity_id: MarketId | SelectionId | str) -> Market | None:
        direct = self.markets.get(cast(MarketId, entity_id))
        if direct is not None:
            return direct
        last_colon = entity_id.rfind(":")
        if last_colon == -1:
            return None
        return self.markets.get(cast(MarketId, entity_id[:last_colon]))

    def get_selection(self, selection_id: SelectionId) -> Selection | None:
        market = self.get_market(selection_id)
        return None if market is None else market.get_selection(selection_id)

    def _with_updated_market(self, market_to_update: Market) -> SportEvent:
        if market_to_update.id not in self.markets:
            raise RuntimeError(f"Market {market_to_update.id!r} not found in {self.id}")
        new = {**self.markets, market_to_update.id: market_to_update}
        return self._clone_with_markets(new.values())

    def _with_updated_prices(self, prices: Mapping[SelectionId, float]) -> SportEvent:
        if not prices:
            return self
        first_sel_id = next(iter(prices.keys()))
        market_id = get_market_id(first_sel_id)
        market = self.markets.get(market_id)
        if market is None:
            raise RuntimeError(f"Market {market_id!r} not found in {self.id}")
        for sel_id in prices:
            if get_market_id(sel_id) != market.id:
                raise RuntimeError("Selections are not all from the same market")
        return self._with_updated_market(market._with_updated_prices(prices))

    def _clone_with_markets(self, markets: Iterable[Market]) -> SportEvent:
        return replace(self, markets=_wrap_markets(markets))


@dataclass(frozen=True, slots=True, kw_only=True)
class UnknownSportEvent(SportEvent):
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        SportEvent.__post_init__(self)
        object.__setattr__(self, "raw", _freeze_mapping(self.raw))


@dataclass(frozen=True, slots=True, kw_only=True)
class HomeAwaySportEvent(SportEvent):
    home_team: str = ""
    away_team: str = ""

    @property
    def name(self) -> str:
        return f"{self.home_team} / {self.away_team}"


@dataclass(frozen=True, slots=True, kw_only=True)
class CompetitorPairSportEvent(SportEvent):
    competitor1: str = ""
    competitor2: str = ""

    @property
    def name(self) -> str:
        return f"{self.competitor1} / {self.competitor2}"


class AmericanFootballMatch(HomeAwaySportEvent):
    pass


class BaseballMatch(HomeAwaySportEvent):
    pass


class BasketballMatch(HomeAwaySportEvent):
    pass


class CricketMatch(HomeAwaySportEvent):
    pass


class FootballMatch(HomeAwaySportEvent):
    pass


class HandballMatch(HomeAwaySportEvent):
    pass


class HockeyMatch(HomeAwaySportEvent):
    pass


class RugbyLeagueMatch(HomeAwaySportEvent):
    pass


class BoxingFight(CompetitorPairSportEvent):
    pass


class MmaFight(CompetitorPairSportEvent):
    pass


class TennisMatch(CompetitorPairSportEvent):
    pass


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


_HOME_AWAY_EVENTS: dict[str, type[HomeAwaySportEvent]] = {
    "se:american_football_match": AmericanFootballMatch,
    "se:baseball_match": BaseballMatch,
    "se:basketball_match": BasketballMatch,
    "se:cricket_match": CricketMatch,
    "se:football_match": FootballMatch,
    "se:handball_match": HandballMatch,
    "se:hockey_match": HockeyMatch,
    "se:rugby_league_match": RugbyLeagueMatch,
}
_COMPETITOR_EVENTS: dict[str, type[CompetitorPairSportEvent]] = {
    "se:boxing_fight": BoxingFight,
    "se:mma_fight": MmaFight,
    "se:tennis_match": TennisMatch,
}


def sport_event_from_json(data: dict[str, Any], *, strict: bool = False) -> SportEvent:
    kind = str(data["kind"])
    markets = tuple(market_from_json(m, strict=strict) for m in data.get("markets", []))
    common_kwargs: dict[str, Any] = {
        "id": SportEventId(str(data["id"])),
        "kind": kind,
        "competition": data["competition"],
        "markets": markets,
        "sport_region": data.get("sportRegion"),
        "start_date": _parse_iso_datetime(data["startDate"]) if data.get("startDate") else None,
        "match_url": data.get("matchUrl"),
    }
    if kind in _HOME_AWAY_EVENTS:
        home_away_cls = _HOME_AWAY_EVENTS[kind]
        return home_away_cls(**common_kwargs, home_team=data["homeTeam"], away_team=data["awayTeam"])
    if kind in _COMPETITOR_EVENTS:
        competitor_cls = _COMPETITOR_EVENTS[kind]
        return competitor_cls(**common_kwargs, competitor1=data["competitor1"], competitor2=data["competitor2"])
    if strict:
        raise ValueError(f"Unknown sport event kind: {kind!r}")
    return UnknownSportEvent(**common_kwargs, raw=data)
