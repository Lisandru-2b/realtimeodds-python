"""Market entities and JSON deserialization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

from .._types import (
    SPORT_OF_SPORT_EVENT_NAMES,
    BasketballPeriod,
    BasketballTotalScope,
    Bookmaker,
    MarketId,
    MarketKind,
    PlayerPropType,
    SelectionId,
    SelectionKind,
    SelectionResult,
    Sport,
    TennisTotalScope,
    TennisUnit,
)
from ..id_helper import get_bookmaker
from .selection import Selection


def _wrap_selections(
    selections: Mapping[SelectionId, Selection] | Iterable[Selection],
) -> Mapping[SelectionId, Selection]:
    if isinstance(selections, Mapping):
        d = dict(selections)
    else:
        d = {s.id: s for s in selections}
    return MappingProxyType(d)


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(data or {}))


_PERIOD_LABELS: dict[str, str] = {
    "full_match": "",
    "1st_half": " (1ere mi-temps)",
    "2nd_half": " (2eme mi-temps)",
    "1st_quarter": " (1er quart-temps)",
    "2nd_quarter": " (2eme quart-temps)",
    "3rd_quarter": " (3eme quart-temps)",
    "4th_quarter": " (4eme quart-temps)",
    "1st_period": " (1ere periode)",
    "2nd_period": " (2eme periode)",
    "3rd_period": " (3eme periode)",
    "1st_set": " (1er set)",
    "2nd_set": " (2eme set)",
    "3rd_set": " (3eme set)",
    "4th_set": " (4eme set)",
    "5th_set": " (5eme set)",
    "1st_inning": " (1ere manche)",
    "overtime": " (prolongation)",
}


def _period_label(period: str | None) -> str:
    return _PERIOD_LABELS.get(period or "full_match", "")


def _format_handicap(value: float) -> str:
    return f"+{value}" if value > 0 else str(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class Market:
    id: MarketId
    kind: str
    selection_kind: SelectionKind
    is_synthetic: bool
    selections: Mapping[SelectionId, Selection] = field(default_factory=dict)

    def __post_init__(self) -> None:
        wrapped = _wrap_selections(self.selections)
        object.__setattr__(self, "selections", wrapped)

        seen_results: set[SelectionResult] = set()
        for sel in self.selections.values():
            if sel.kind != self.selection_kind:
                raise ValueError(
                    f"Selection kind {sel.kind!r} is not compatible with market kind {self.kind!r}"
                )
            if sel.result in seen_results:
                raise ValueError(f"Selection result {sel.result!r} appears multiple times")
            seen_results.add(sel.result)

    @property
    def bookmaker(self) -> Bookmaker:
        return get_bookmaker(self.id)

    @property
    def market_name(self) -> str:
        return self.kind.split(":")[1].split(".")[1] if ":" in self.kind and "." in self.kind else self.kind

    @property
    def sport_event_name(self) -> str:
        return self.kind.split(":")[1].split(".")[0] if ":" in self.kind and "." in self.kind else "unknown"

    @property
    def sport(self) -> Sport:
        return SPORT_OF_SPORT_EVENT_NAMES[self.sport_event_name]

    @property
    def is_available(self) -> bool:
        return any(s.is_available for s in self.selections.values())

    @property
    def is_fully_available(self) -> bool:
        return self.are_all_selections_present and all(s.is_available for s in self.selections.values())

    @property
    def are_all_selections_present(self) -> bool:
        return len(self.selections) == self.number_of_possible_results

    @property
    def number_of_possible_results(self) -> int:
        return Selection.number_of_results(self.selection_kind)

    @property
    def category(self) -> str:
        return self.market_name

    def get_selection(self, selection_id: SelectionId) -> Selection | None:
        return self.selections.get(selection_id)

    def get_selection_by_result(self, result: SelectionResult) -> Selection | None:
        for sel in self.selections.values():
            if sel.result == result:
                return sel
        return None

    def get_selections_except_for_result(self, result: SelectionResult) -> list[Selection]:
        return [s for s in self.selections.values() if s.result != result]

    def get_result(self, selection_id: SelectionId) -> SelectionResult | None:
        sel = self.get_selection(selection_id)
        return sel.result if sel is not None else None

    def is_selection_available(self, result: SelectionResult) -> bool:
        sel = self.get_selection_by_result(result)
        return bool(sel and sel.is_available)

    def calculate_margin(self) -> float:
        if not self.is_fully_available:
            raise RuntimeError("All selections are not available")
        margin = 0.0
        for sel in self.selections.values():
            assert sel.quote is not None
            margin += sel.quote.implied_probability
        return margin - 1.0

    def is_fair_odd_available(self, result: SelectionResult) -> bool:
        return self.is_selection_available(result) if self.is_synthetic else self.is_fully_available

    def get_fair_odd(self, result: SelectionResult) -> float:
        if self.is_synthetic:
            sel = self.get_selection_by_result(result)
            if sel is None or not sel.is_available:
                raise RuntimeError(f"Synthetic market {self.id} cannot compute fair odd for {result!r}")
            return sel.price
        if not self.is_fully_available:
            raise RuntimeError(f"Market {self.id} is not fully available")
        sel = self.get_selection_by_result(result)
        if sel is None:
            raise RuntimeError(f"Selection {result!r} not found in market {self.id}")
        n = len(self.selections)
        margin = self.calculate_margin()
        return (n * sel.price) / (n - sel.price * margin)

    def are_prices_different(self, prices: Mapping[SelectionId, float]) -> bool:
        for sel_id, price in prices.items():
            sel = self.get_selection(sel_id)
            if sel is None or not sel.is_available:
                return True
            assert sel.quote is not None
            if price != sel.quote.price:
                return True
        return False

    def get_selection_name(self, result: SelectionResult) -> str:
        return result

    def _with_selections(self, new_selections: Iterable[Selection]) -> Market:
        return replace(self, selections=_wrap_selections(new_selections))

    def _with_updated_selection(self, sel_to_update: Selection) -> Market:
        if sel_to_update.id not in self.selections:
            raise RuntimeError(f"Selection {sel_to_update.id!r} not found in market {self.id}")
        new = {**self.selections, sel_to_update.id: sel_to_update}
        return self._with_selections(new.values())

    def _with_updated_price(self, selection_id: SelectionId, price: float) -> Market:
        sel = self.get_selection(selection_id)
        if sel is None:
            raise RuntimeError(f"Selection {selection_id!r} not found")
        return self._with_updated_selection(sel._with_price(price))

    def _with_updated_prices(self, prices: Mapping[SelectionId, float]) -> Market:
        if not prices:
            return self
        new = dict(self.selections)
        for sel_id, price in prices.items():
            sel = self.get_selection(sel_id)
            if sel is None:
                raise RuntimeError(f"Selection {sel_id!r} not found")
            new[sel_id] = sel._with_price(price)
        return self._with_selections(new.values())

    def _with_unavailable_selection(self, selection_id: SelectionId) -> Market:
        sel = self.get_selection(selection_id)
        if sel is None:
            raise RuntimeError(f"Selection {selection_id!r} not found")
        return self._with_updated_selection(sel._with_unavailability())


@dataclass(frozen=True, slots=True, kw_only=True)
class UnknownMarket(Market):
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Market.__post_init__(self)
        object.__setattr__(self, "raw", _freeze_mapping(self.raw))

    @property
    def category(self) -> str:
        return "unknown"


@dataclass(frozen=True, slots=True, kw_only=True)
class HomeAwayMoneyline(Market):
    home_team: str
    away_team: str
    period: str = "full_match"

    @property
    def category(self) -> str:
        return "Moneyline"

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _period_label(self.period)
        if result == "home":
            return f"{self.home_team} vainqueur{suffix}"
        if result == "away":
            return f"{self.away_team} vainqueur{suffix}"
        if result == "draw":
            return "Match nul"
        raise ValueError(f"Invalid selection result: {result}")


@dataclass(frozen=True, slots=True, kw_only=True)
class HomeAwayHandicap(Market):
    home_team: str
    away_team: str
    period: str
    handicap: float

    @property
    def category(self) -> str:
        return "Handicap"

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _period_label(self.period)
        if result == "home":
            return f"{self.home_team} {_format_handicap(self.handicap)}{suffix}"
        if result == "away":
            return f"{self.away_team} {_format_handicap(-self.handicap)}{suffix}"
        raise ValueError(f"Invalid selection result: {result}")


@dataclass(frozen=True, slots=True, kw_only=True)
class HomeAwayTotal(Market):
    home_team: str
    away_team: str
    period: str
    scope: BasketballTotalScope
    cut: float

    @property
    def category(self) -> str:
        return "Total"

    def _scope_subject(self) -> str:
        if self.scope == "match":
            return "Total combine"
        if self.scope == "home":
            return self.home_team
        return self.away_team

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _period_label(self.period)
        if result not in ("over", "under"):
            raise ValueError(f"Invalid selection result: {result}")
        verb = "plus de" if result == "over" else "moins de"
        return f"{self._scope_subject()} : {verb} {self.cut}{suffix}"


@dataclass(frozen=True, slots=True, kw_only=True)
class CompetitorMoneyline(Market):
    competitor1: str
    competitor2: str
    period: str = "full_match"

    @property
    def category(self) -> str:
        return "Moneyline"

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _period_label(self.period)
        if result == "competitor1":
            return f"{self.competitor1} vainqueur{suffix}"
        if result == "competitor2":
            return f"{self.competitor2} vainqueur{suffix}"
        raise ValueError(f"Invalid selection result: {result}")


@dataclass(frozen=True, slots=True, kw_only=True)
class CompetitorHandicap(Market):
    competitor1: str
    competitor2: str
    period: str
    unit: TennisUnit
    handicap: float

    @property
    def category(self) -> str:
        return "Handicap"

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _period_label(self.period)
        if result == "competitor1":
            return f"{self.competitor1} {_format_handicap(self.handicap)} {self.unit}{suffix}"
        if result == "competitor2":
            return f"{self.competitor2} {_format_handicap(-self.handicap)} {self.unit}{suffix}"
        raise ValueError(f"Invalid selection result: {result}")


@dataclass(frozen=True, slots=True, kw_only=True)
class CompetitorTotal(Market):
    competitor1: str
    competitor2: str
    period: str
    scope: TennisTotalScope
    unit: TennisUnit
    cut: float

    @property
    def category(self) -> str:
        return "Total"

    def _scope_subject(self) -> str:
        if self.scope == "match":
            return "Total combine"
        if self.scope == "competitor1":
            return self.competitor1
        return self.competitor2

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _period_label(self.period)
        if result not in ("over", "under"):
            raise ValueError(f"Invalid selection result: {result}")
        verb = "plus de" if result == "over" else "moins de"
        return f"{self._scope_subject()} : {verb} {self.cut} {self.unit}{suffix}"


class AmericanFootballMoneyline(HomeAwayMoneyline):
    pass


class AmericanFootballHandicap(HomeAwayHandicap):
    pass


class AmericanFootballTotal(HomeAwayTotal):
    pass


class BaseballMoneyline(HomeAwayMoneyline):
    pass


class BaseballHandicap(HomeAwayHandicap):
    pass


class BaseballTotal(HomeAwayTotal):
    pass


class BasketballMoneyline(HomeAwayMoneyline):
    period: BasketballPeriod = "full_match"


class BasketballHandicap(HomeAwayHandicap):
    pass


class BasketballTotal(HomeAwayTotal):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class BasketballPlayerPropOverUnder(Market):
    player_name: str
    prop_type: PlayerPropType
    cut: float

    @property
    def category(self) -> str:
        return "NBA"

    def get_selection_name(self, result: SelectionResult) -> str:
        if result not in ("over", "under"):
            raise ValueError(f"Invalid selection result: {result}")
        comparator = "plus de" if result == "over" else "moins de"
        return f"{self.player_name} {comparator} {self.cut} {self.prop_type}"


class BoxingMoneyline(CompetitorMoneyline):
    pass


class CricketMoneyline(HomeAwayMoneyline):
    pass


class FootballMoneyline(HomeAwayMoneyline):
    pass


class FootballHandicap(HomeAwayHandicap):
    pass


class FootballTotal(HomeAwayTotal):
    pass


class HandballMoneyline(HomeAwayMoneyline):
    pass


class HandballHandicap(HomeAwayHandicap):
    pass


class HandballTotal(HomeAwayTotal):
    pass


class HockeyMoneyline(HomeAwayMoneyline):
    pass


class HockeyRegulationMoneyline(HomeAwayMoneyline):
    pass


class HockeyHandicap(HomeAwayHandicap):
    pass


class HockeyTotal(HomeAwayTotal):
    pass


class MmaMoneyline(CompetitorMoneyline):
    pass


class RugbyLeagueMoneyline(HomeAwayMoneyline):
    pass


class RugbyLeagueHandicap(HomeAwayHandicap):
    pass


class RugbyLeagueTotal(HomeAwayTotal):
    pass


class TennisMoneyline(CompetitorMoneyline):
    pass


class TennisHandicap(CompetitorHandicap):
    pass


class TennisTotal(CompetitorTotal):
    pass


_HOME_AWAY_MONEYLINE: dict[str, type[HomeAwayMoneyline]] = {
    "market:american_football_match.moneyline": AmericanFootballMoneyline,
    "market:baseball_match.moneyline": BaseballMoneyline,
    "market:basketball_match.moneyline": BasketballMoneyline,
    "market:cricket_match.moneyline": CricketMoneyline,
    "market:football_match.moneyline": FootballMoneyline,
    "market:handball_match.moneyline": HandballMoneyline,
    "market:hockey_match.moneyline": HockeyMoneyline,
    "market:hockey_match.regulation_moneyline": HockeyRegulationMoneyline,
    "market:rugby_league_match.moneyline": RugbyLeagueMoneyline,
}
_HOME_AWAY_HANDICAP: dict[str, type[HomeAwayHandicap]] = {
    "market:american_football_match.handicap": AmericanFootballHandicap,
    "market:baseball_match.handicap": BaseballHandicap,
    "market:basketball_match.handicap": BasketballHandicap,
    "market:football_match.handicap": FootballHandicap,
    "market:handball_match.handicap": HandballHandicap,
    "market:hockey_match.handicap": HockeyHandicap,
    "market:rugby_league_match.handicap": RugbyLeagueHandicap,
}
_HOME_AWAY_TOTAL: dict[str, type[HomeAwayTotal]] = {
    "market:american_football_match.total": AmericanFootballTotal,
    "market:baseball_match.total": BaseballTotal,
    "market:basketball_match.total": BasketballTotal,
    "market:football_match.total": FootballTotal,
    "market:handball_match.total": HandballTotal,
    "market:hockey_match.total": HockeyTotal,
    "market:rugby_league_match.total": RugbyLeagueTotal,
}
_COMPETITOR_MONEYLINE: dict[str, type[CompetitorMoneyline]] = {
    "market:boxing_fight.moneyline": BoxingMoneyline,
    "market:mma_fight.moneyline": MmaMoneyline,
    "market:tennis_match.moneyline": TennisMoneyline,
}


def market_from_json(data: dict[str, Any], *, strict: bool = False) -> Market:
    kind = str(data["kind"])
    selections = tuple(Selection._from_json(s) for s in data.get("selections", []))
    common_kwargs: dict[str, Any] = {
        "id": MarketId(str(data["id"])),
        "kind": kind,
        "selection_kind": data["selectionKind"],
        "is_synthetic": bool(data.get("isSynthetic", False)),
        "selections": selections,
    }
    if kind in _HOME_AWAY_MONEYLINE:
        moneyline_cls = _HOME_AWAY_MONEYLINE[kind]
        return moneyline_cls(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
            period=data.get("period", "full_match"),
        )
    if kind in _HOME_AWAY_HANDICAP:
        handicap_cls = _HOME_AWAY_HANDICAP[kind]
        return handicap_cls(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
            period=data.get("period", "full_match"),
            handicap=float(data["handicap"]),
        )
    if kind in _HOME_AWAY_TOTAL:
        total_cls = _HOME_AWAY_TOTAL[kind]
        return total_cls(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
            period=data.get("period", "full_match"),
            scope=data["scope"],
            cut=float(data["cut"]),
        )
    if kind == "market:basketball_match.player_prop_over_under":
        return BasketballPlayerPropOverUnder(
            **common_kwargs,
            player_name=data["playerName"],
            prop_type=data["propType"],
            cut=float(data["cut"]),
        )
    if kind in _COMPETITOR_MONEYLINE:
        competitor_cls = _COMPETITOR_MONEYLINE[kind]
        return competitor_cls(
            **common_kwargs,
            competitor1=data["competitor1"],
            competitor2=data["competitor2"],
            period=data.get("period", "full_match"),
        )
    if kind == "market:tennis_match.handicap":
        return TennisHandicap(
            **common_kwargs,
            competitor1=data["competitor1"],
            competitor2=data["competitor2"],
            period=data.get("period", "full_match"),
            unit=data["unit"],
            handicap=float(data["handicap"]),
        )
    if kind == "market:tennis_match.total":
        return TennisTotal(
            **common_kwargs,
            competitor1=data["competitor1"],
            competitor2=data["competitor2"],
            period=data.get("period", "full_match"),
            scope=data["scope"],
            unit=data["unit"],
            cut=float(data["cut"]),
        )
    if strict:
        raise ValueError(f"Unknown market kind: {kind!r}")
    return UnknownMarket(**common_kwargs, raw=data)
