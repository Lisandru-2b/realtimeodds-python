"""Market — a betting market within a sport event.

Discriminated union over `kind`. Six variants in v1:
  - BasketballMoneyline / BasketballHandicap / BasketballTotal /
    BasketballPlayerPropOverUnder
  - FootballMoneyline
  - TennisMoneyline
"""

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
)
from ..id_helper import get_bookmaker
from .selection import Selection


def _wrap_selections(
    selections: Mapping[SelectionId, Selection] | Iterable[Selection],
) -> Mapping[SelectionId, Selection]:
    """Build a read-only `MappingProxyType` keyed by selection id."""
    if isinstance(selections, Mapping):
        d = dict(selections)
    else:
        d = {s.id: s for s in selections}
    return MappingProxyType(d)


_BASKETBALL_PERIOD_LABELS: dict[BasketballPeriod, str] = {
    "full_match": "",
    "1st_half": " (1ère mi-temps)",
    "2nd_half": " (2ème mi-temps)",
    "1st_quarter": " (1er quart-temps)",
    "2nd_quarter": " (2ème quart-temps)",
    "3rd_quarter": " (3ème quart-temps)",
    "4th_quarter": " (4ème quart-temps)",
    "overtime": " (prolongation)",
}


def _format_handicap(value: float) -> str:
    return f"+{value}" if value > 0 else str(value)


# ─── Base ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class Market:
    """Abstract base for all market variants. All fields are read-only.

    Consumers should branch on ``market.kind`` to access subtype-specific
    fields (e.g. ``BasketballHandicap.handicap``). Static type checkers can
    narrow via ``isinstance`` or by comparing ``kind`` to a literal.
    """

    id: MarketId
    kind: MarketKind
    selection_kind: SelectionKind
    is_synthetic: bool
    selections: Mapping[SelectionId, Selection] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize to a frozen mapping, then validate uniqueness/coherence.
        wrapped = _wrap_selections(self.selections)
        object.__setattr__(self, "selections", wrapped)

        seen_results: set[SelectionResult] = set()
        for sel in self.selections.values():
            if sel.kind != self.selection_kind:
                raise ValueError(
                    f"Selection kind {sel.kind!r} is not compatible with "
                    f"market kind {self.kind!r}"
                )
            if sel.result in seen_results:
                raise ValueError(
                    f"Selection result {sel.result!r} appears multiple times"
                )
            seen_results.add(sel.result)

    # ─── Computed properties ────────────────────────────────────────────────

    @property
    def bookmaker(self) -> Bookmaker:
        return get_bookmaker(self.id)

    @property
    def market_name(self) -> str:
        # `market:<sport_event_name>.<market_name>` -> `<market_name>`
        return self.kind.split(":")[1].split(".")[1]

    @property
    def sport_event_name(self) -> str:
        return self.kind.split(":")[1].split(".")[0]

    @property
    def sport(self) -> Sport:
        return SPORT_OF_SPORT_EVENT_NAMES[self.sport_event_name]

    @property
    def is_available(self) -> bool:
        return any(s.is_available for s in self.selections.values())

    @property
    def is_fully_available(self) -> bool:
        if not self.are_all_selections_present:
            return False
        return all(s.is_available for s in self.selections.values())

    @property
    def are_all_selections_present(self) -> bool:
        return len(self.selections) == self.number_of_possible_results

    @property
    def number_of_possible_results(self) -> int:
        return Selection.number_of_results(self.selection_kind)

    @property
    def category(self) -> str:
        """Subclass-overridable human-readable category. Default falls back to `market_name`."""
        return self.market_name

    # ─── Lookups ────────────────────────────────────────────────────────────

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

    # ─── Margin / fair odds ─────────────────────────────────────────────────

    def calculate_margin(self) -> float:
        """Sum of implied probabilities minus 1. Raises if the market is not fully available."""
        if not self.is_fully_available:
            raise RuntimeError("All selections are not available")
        margin = 0.0
        for sel in self.selections.values():
            assert sel.quote is not None  # guaranteed by is_fully_available
            margin += sel.quote.implied_probability
        return margin - 1.0

    def is_fair_odd_available(self, result: SelectionResult) -> bool:
        if self.is_synthetic:
            return self.is_selection_available(result)
        return self.is_fully_available

    def get_fair_odd(self, result: SelectionResult) -> float:
        """Margin-adjusted "true" odd for `result`. Synthetic markets bypass the margin computation."""
        if self.is_synthetic:
            sel = self.get_selection_by_result(result)
            if sel is None or not sel.is_available:
                raise RuntimeError(
                    f"Synthetic market {self.id} cannot compute fair odd for {result!r}"
                )
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
        """Default fallback. Subclasses override with sport-specific human-readable strings."""
        return result

    # ─── Internal mutators (return new instance) ────────────────────────────

    def _with_selections(self, new_selections: Iterable[Selection]) -> Market:
        """Subclass-aware clone with replaced selections. Override per subclass."""
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


# ─── Subclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class BasketballMoneyline(Market):
    home_team: str
    away_team: str
    period: BasketballPeriod = "full_match"

    @property
    def category(self) -> str:
        return "Moneyline"

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _BASKETBALL_PERIOD_LABELS[self.period]
        if result == "home":
            return f"{self.home_team} vainqueur{suffix}"
        if result == "away":
            return f"{self.away_team} vainqueur{suffix}"
        raise ValueError(f"Invalid selection result: {result}")


@dataclass(frozen=True, slots=True, kw_only=True)
class BasketballHandicap(Market):
    home_team: str
    away_team: str
    period: BasketballPeriod
    handicap: float

    @property
    def category(self) -> str:
        return "Handicap"

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _BASKETBALL_PERIOD_LABELS[self.period]
        if result == "home":
            return f"{self.home_team} {_format_handicap(self.handicap)}{suffix}"
        if result == "away":
            return f"{self.away_team} {_format_handicap(-self.handicap)}{suffix}"
        raise ValueError(f"Invalid selection result: {result}")


@dataclass(frozen=True, slots=True, kw_only=True)
class BasketballTotal(Market):
    home_team: str
    away_team: str
    period: BasketballPeriod
    scope: BasketballTotalScope
    cut: float

    @property
    def category(self) -> str:
        return "Total"

    def _scope_subject(self) -> str:
        if self.scope == "match":
            return "Total combiné"
        if self.scope == "home":
            return self.home_team
        return self.away_team

    def get_selection_name(self, result: SelectionResult) -> str:
        suffix = _BASKETBALL_PERIOD_LABELS[self.period]
        if result not in ("over", "under"):
            raise ValueError(f"Invalid selection result: {result}")
        verb = "plus de" if result == "over" else "moins de"
        return f"{self._scope_subject()} : {verb} {self.cut} points{suffix}"


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
        verbs: dict[PlayerPropType, str] = {
            "points": "marque",
            "rebounds": "effectue",
            "assists": "fait",
            "threes": "marque",
            "steals": "fait",
            "blocks": "fait",
            "points_rebounds": "effectue",
            "points_assists": "effectue",
            "rebounds_assists": "effectue",
            "points_rebounds_assists": "effectue",
            "other": "effectue",
        }
        types: dict[PlayerPropType, str] = {
            "points": "points",
            "rebounds": "rebonds",
            "assists": "passes décisives",
            "threes": "tirs à trois points",
            "steals": "interceptions",
            "blocks": "contres",
            "points_rebounds": "points + rebonds",
            "points_assists": "points + passes décisives",
            "rebounds_assists": "rebonds + passes décisives",
            "points_rebounds_assists": "points + rebonds + passes décisives",
            "other": "autre",
        }
        comparator = "plus de" if result == "over" else "moins de"
        return f"{self.player_name} {verbs[self.prop_type]} {comparator} {self.cut} {types[self.prop_type]}"


@dataclass(frozen=True, slots=True, kw_only=True)
class FootballMoneyline(Market):
    home_team: str
    away_team: str

    @property
    def category(self) -> str:
        return "Moneyline"

    def get_selection_name(self, result: SelectionResult) -> str:
        if result == "home":
            return f"{self.home_team} vainqueur"
        if result == "away":
            return f"{self.away_team} vainqueur"
        if result == "draw":
            return "Match nul"
        raise ValueError(f"Invalid selection result: {result}")


@dataclass(frozen=True, slots=True, kw_only=True)
class TennisMoneyline(Market):
    competitor1: str
    competitor2: str

    @property
    def category(self) -> str:
        return "Moneyline"

    def get_selection_name(self, result: SelectionResult) -> str:
        if result == "competitor1":
            return f"{self.competitor1} vainqueur"
        if result == "competitor2":
            return f"{self.competitor2} vainqueur"
        raise ValueError(f"Invalid selection result: {result}")


# ─── JSON deserialization ──────────────────────────────────────────────────


def market_from_json(data: dict[str, Any]) -> Market:
    """Build the right Market subclass from its wire JSON. Mirrors `Market.fromJSON` in JS."""
    kind: MarketKind = data["kind"]
    selections = tuple(Selection._from_json(s) for s in data.get("selections", []))
    common_kwargs: dict[str, Any] = {
        "id": MarketId(str(data["id"])),
        "kind": kind,
        "selection_kind": data["selectionKind"],
        "is_synthetic": bool(data.get("isSynthetic", False)),
        "selections": selections,
    }
    if kind == "market:basketball_match.moneyline":
        return BasketballMoneyline(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
            period=data.get("period", "full_match"),
        )
    if kind == "market:basketball_match.handicap":
        return BasketballHandicap(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
            period=data["period"],
            handicap=float(data["handicap"]),
        )
    if kind == "market:basketball_match.total":
        return BasketballTotal(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
            period=data["period"],
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
    if kind == "market:football_match.moneyline":
        return FootballMoneyline(
            **common_kwargs,
            home_team=data["homeTeam"],
            away_team=data["awayTeam"],
        )
    if kind == "market:tennis_match.moneyline":
        return TennisMoneyline(
            **common_kwargs,
            competitor1=data["competitor1"],
            competitor2=data["competitor2"],
        )
    raise ValueError(f"Unknown market kind: {kind!r}")
