"""SportEvent — a sport match reported by a bookmaker.

Discriminated union over `kind`. Three variants in v1:
  - BasketballMatch
  - FootballMatch
  - TennisMatch
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from .._id_helper import get_bookmaker, get_market_id
from .._types import (
    SPORT_OF_SPORT_EVENT_NAMES,
    Bookmaker,
    MarketId,
    SelectionId,
    Sport,
    SportEventId,
    SportEventKind,
)
from .market import Market, market_from_json
from .selection import Selection


def _wrap_markets(markets: Mapping[MarketId, Market] | Iterable[Market]) -> Mapping[MarketId, Market]:
    if isinstance(markets, Mapping):
        d = dict(markets)
    else:
        d = {m.id: m for m in markets}
    return MappingProxyType(d)


# ─── Base ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class SportEvent:
    """Abstract base for all sport event variants. All fields are read-only."""

    id: SportEventId
    kind: SportEventKind
    competition: str
    markets: Mapping[MarketId, Market] = field(default_factory=dict)
    sport_region: str | None = None
    start_date: datetime | None = None
    match_url: str | None = None

    def __post_init__(self) -> None:
        wrapped = _wrap_markets(self.markets)
        object.__setattr__(self, "markets", wrapped)

        for market in self.markets.values():
            if market.sport_event_name != self.sport_event_name:
                raise ValueError(
                    f"Market kind {market.kind!r} is not compatible with sport event kind {self.kind!r}"
                )

    # ─── Computed properties ────────────────────────────────────────────────

    @property
    def bookmaker(self) -> Bookmaker:
        return get_bookmaker(self.id)

    @property
    def sport_event_name(self) -> str:
        # `se:<sport_event_name>` -> `<sport_event_name>`
        return self.kind.split(":")[1]

    @property
    def sport(self) -> Sport:
        return SPORT_OF_SPORT_EVENT_NAMES[self.sport_event_name]

    @property
    def name(self) -> str:
        """Human-readable match name. Subclasses override."""
        return self.id  # fallback

    # ─── Lookups ────────────────────────────────────────────────────────────

    def get_market(self, entity_id: MarketId | SelectionId | str) -> Market | None:
        """Lookup by MarketId or SelectionId (truncated to MarketId)."""
        try:
            market_id = get_market_id(entity_id)
        except ValueError:
            return None
        return self.markets.get(market_id)

    def get_selection(self, selection_id: SelectionId) -> Selection | None:
        market = self.get_market(selection_id)
        if market is None:
            return None
        return market.get_selection(selection_id)

    # ─── Internal mutators ──────────────────────────────────────────────────

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
        new_market = market._with_updated_prices(prices)
        return self._with_updated_market(new_market)

    def _clone_with_markets(self, markets: Iterable[Market]) -> SportEvent:
        """Override per subclass — returns the right concrete type with replaced markets."""
        raise NotImplementedError


# ─── Subclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class BasketballMatch(SportEvent):
    home_team: str = ""
    away_team: str = ""

    @property
    def name(self) -> str:
        return f"{self.home_team} / {self.away_team}"

    def _clone_with_markets(self, markets: Iterable[Market]) -> BasketballMatch:
        return BasketballMatch(
            id=self.id,
            kind=self.kind,
            competition=self.competition,
            markets=_wrap_markets(markets),
            sport_region=self.sport_region,
            start_date=self.start_date,
            match_url=self.match_url,
            home_team=self.home_team,
            away_team=self.away_team,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FootballMatch(SportEvent):
    home_team: str = ""
    away_team: str = ""

    @property
    def name(self) -> str:
        return f"{self.home_team} / {self.away_team}"

    def _clone_with_markets(self, markets: Iterable[Market]) -> FootballMatch:
        return FootballMatch(
            id=self.id,
            kind=self.kind,
            competition=self.competition,
            markets=_wrap_markets(markets),
            sport_region=self.sport_region,
            start_date=self.start_date,
            match_url=self.match_url,
            home_team=self.home_team,
            away_team=self.away_team,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TennisMatch(SportEvent):
    competitor1: str = ""
    competitor2: str = ""

    @property
    def name(self) -> str:
        return f"{self.competitor1} / {self.competitor2}"

    def _clone_with_markets(self, markets: Iterable[Market]) -> TennisMatch:
        return TennisMatch(
            id=self.id,
            kind=self.kind,
            competition=self.competition,
            markets=_wrap_markets(markets),
            sport_region=self.sport_region,
            start_date=self.start_date,
            match_url=self.match_url,
            competitor1=self.competitor1,
            competitor2=self.competitor2,
        )


# ─── JSON deserialization ──────────────────────────────────────────────────


def _parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string into a timezone-aware datetime (UTC if offsetless)."""
    # Python 3.10 fromisoformat doesn't accept 'Z', normalize it.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def sport_event_from_json(data: dict[str, Any]) -> SportEvent:
    """Build the right SportEvent subclass from its wire JSON. Mirrors `SportEvent.fromJSON` in JS."""
    kind: SportEventKind = data["kind"]
    markets = tuple(market_from_json(m) for m in data.get("markets", []))
    common_kwargs: dict[str, Any] = {
        "id": SportEventId(str(data["id"])),
        "kind": kind,
        "competition": data["competition"],
        "markets": markets,
        "sport_region": data.get("sportRegion"),
        "start_date": _parse_iso_datetime(data["startDate"]) if data.get("startDate") else None,
        "match_url": data.get("matchUrl"),
    }
    if kind == "se:basketball_match":
        return BasketballMatch(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
        )
    if kind == "se:football_match":
        return FootballMatch(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
        )
    if kind == "se:tennis_match":
        return TennisMatch(
            **common_kwargs,
            competitor1=data["competitor1"],
            competitor2=data["competitor2"],
        )
    raise ValueError(f"Unknown sport event kind: {kind!r}")
