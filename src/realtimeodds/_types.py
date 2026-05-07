"""Type aliases and literal enums shared across the SDK.

These mirror the spec definitions in `realtimeodds-spec/schemas/v1/common.schema.json`
and the wire-level constants used by the gateway.
"""

from typing import Literal, NewType

# ─── Bookmaker / sport / kinds ──────────────────────────────────────────────

Bookmaker = Literal[
    "ps3838",
    "winamax",
    "betclic",
    "parions_sport",
    "unibet",
    "stake",
    "polymarket",
]

Sport = Literal["basketball", "football", "tennis"]

SportEventKind = Literal[
    "se:basketball_match",
    "se:football_match",
    "se:tennis_match",
]

MarketKind = Literal[
    "market:basketball_match.moneyline",
    "market:basketball_match.handicap",
    "market:basketball_match.total",
    "market:basketball_match.player_prop_over_under",
    "market:football_match.moneyline",
    "market:tennis_match.moneyline",
]

SelectionKind = Literal[
    "over/under",
    "home/draw/away",
    "home/away",
    "competitor1/competitor2",
]

SelectionResult = Literal[
    "over",
    "under",
    "home",
    "draw",
    "away",
    "competitor1",
    "competitor2",
]

BasketballPeriod = Literal[
    "full_match",
    "1st_half",
    "2nd_half",
    "1st_quarter",
    "2nd_quarter",
    "3rd_quarter",
    "4th_quarter",
    "overtime",
]

PlayerPropType = Literal[
    "points",
    "rebounds",
    "assists",
    "threes",
    "steals",
    "blocks",
    "points_rebounds",
    "points_assists",
    "rebounds_assists",
    "points_rebounds_assists",
    "other",
]

BasketballTotalScope = Literal["match", "home", "away"]

# ─── Branded id types ───────────────────────────────────────────────────────
# `NewType` gives us nominal typing while keeping the runtime cost at zero
# (still a `str`). Same intent as the branded EntityId in sb-entities.

SportEventId = NewType("SportEventId", str)
MarketId = NewType("MarketId", str)
SelectionId = NewType("SelectionId", str)
Competition = NewType("Competition", str)


# ─── Mappings (sport_event_name -> sport, kind -> ...) ─────────────────────

SPORT_OF_SPORT_EVENT_NAMES: dict[str, Sport] = {
    "basketball_match": "basketball",
    "football_match": "football",
    "tennis_match": "tennis",
}


# Selection kind ↔ valid results, mirroring SELECTION_RESULT_ASSOCIATIONS in
# sb-entities. Used by Selection() to validate.
SELECTION_RESULT_ASSOCIATIONS: dict[SelectionKind, tuple[SelectionResult, ...]] = {
    "over/under": ("over", "under"),
    "home/draw/away": ("home", "draw", "away"),
    "home/away": ("home", "away"),
    "competitor1/competitor2": ("competitor1", "competitor2"),
}
