"""Type aliases and literal enums shared across the SDK.

These mirror ``realtimeodds-spec/schemas/v1/common.schema.json``.
"""

from typing import Literal, NewType

Bookmaker = Literal[
    "ps3838",
    "winamax",
    "betclic",
    "parions_sport",
    "unibet",
    "stake",
    "polymarket",
]

SPORTS = (
    "american_football",
    "baseball",
    "basketball",
    "boxing",
    "cricket",
    "football",
    "handball",
    "hockey",
    "mma",
    "rugby_league",
    "tennis",
)
Sport = Literal[
    "american_football",
    "baseball",
    "basketball",
    "boxing",
    "cricket",
    "football",
    "handball",
    "hockey",
    "mma",
    "rugby_league",
    "tennis",
]

SPORT_EVENT_KINDS = (
    "se:american_football_match",
    "se:baseball_match",
    "se:basketball_match",
    "se:boxing_fight",
    "se:cricket_match",
    "se:football_match",
    "se:handball_match",
    "se:hockey_match",
    "se:mma_fight",
    "se:rugby_league_match",
    "se:tennis_match",
)
SportEventKind = Literal[
    "se:american_football_match",
    "se:baseball_match",
    "se:basketball_match",
    "se:boxing_fight",
    "se:cricket_match",
    "se:football_match",
    "se:handball_match",
    "se:hockey_match",
    "se:mma_fight",
    "se:rugby_league_match",
    "se:tennis_match",
]

MARKET_KINDS = (
    "market:american_football_match.moneyline",
    "market:american_football_match.handicap",
    "market:american_football_match.total",
    "market:baseball_match.moneyline",
    "market:baseball_match.handicap",
    "market:baseball_match.total",
    "market:basketball_match.moneyline",
    "market:basketball_match.handicap",
    "market:basketball_match.total",
    "market:basketball_match.player_prop_over_under",
    "market:boxing_fight.moneyline",
    "market:cricket_match.moneyline",
    "market:football_match.moneyline",
    "market:football_match.handicap",
    "market:football_match.total",
    "market:handball_match.moneyline",
    "market:handball_match.handicap",
    "market:handball_match.total",
    "market:hockey_match.moneyline",
    "market:hockey_match.regulation_moneyline",
    "market:hockey_match.handicap",
    "market:hockey_match.total",
    "market:mma_fight.moneyline",
    "market:rugby_league_match.moneyline",
    "market:rugby_league_match.handicap",
    "market:rugby_league_match.total",
    "market:tennis_match.moneyline",
    "market:tennis_match.handicap",
    "market:tennis_match.total",
)
MarketKind = Literal[
    "market:american_football_match.moneyline",
    "market:american_football_match.handicap",
    "market:american_football_match.total",
    "market:baseball_match.moneyline",
    "market:baseball_match.handicap",
    "market:baseball_match.total",
    "market:basketball_match.moneyline",
    "market:basketball_match.handicap",
    "market:basketball_match.total",
    "market:basketball_match.player_prop_over_under",
    "market:boxing_fight.moneyline",
    "market:cricket_match.moneyline",
    "market:football_match.moneyline",
    "market:football_match.handicap",
    "market:football_match.total",
    "market:handball_match.moneyline",
    "market:handball_match.handicap",
    "market:handball_match.total",
    "market:hockey_match.moneyline",
    "market:hockey_match.regulation_moneyline",
    "market:hockey_match.handicap",
    "market:hockey_match.total",
    "market:mma_fight.moneyline",
    "market:rugby_league_match.moneyline",
    "market:rugby_league_match.handicap",
    "market:rugby_league_match.total",
    "market:tennis_match.moneyline",
    "market:tennis_match.handicap",
    "market:tennis_match.total",
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

AmericanFootballPeriod = Literal[
    "full_match",
    "1st_half",
    "2nd_half",
    "1st_quarter",
    "2nd_quarter",
    "3rd_quarter",
    "4th_quarter",
    "overtime",
]
BaseballPeriod = Literal["full_match", "1st_half", "1st_inning"]
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
FootballPeriod = Literal["full_match", "1st_half", "2nd_half"]
HandballPeriod = Literal["full_match", "1st_half", "2nd_half"]
HockeyPeriod = Literal["full_match", "1st_period", "2nd_period", "3rd_period"]
RugbyLeaguePeriod = Literal["full_match", "1st_half", "2nd_half"]
TennisPeriod = Literal["full_match", "1st_set", "2nd_set", "3rd_set", "4th_set", "5th_set"]

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

TotalScope = Literal["match", "home", "away"]
BasketballTotalScope = TotalScope
TennisTotalScope = Literal["match", "competitor1", "competitor2"]
TennisUnit = Literal["sets", "games"]

SportEventId = NewType("SportEventId", str)
MarketId = NewType("MarketId", str)
SelectionId = NewType("SelectionId", str)
Competition = NewType("Competition", str)

SPORT_OF_SPORT_EVENT_NAMES: dict[str, Sport] = {
    "american_football_match": "american_football",
    "baseball_match": "baseball",
    "basketball_match": "basketball",
    "boxing_fight": "boxing",
    "cricket_match": "cricket",
    "football_match": "football",
    "handball_match": "handball",
    "hockey_match": "hockey",
    "mma_fight": "mma",
    "rugby_league_match": "rugby_league",
    "tennis_match": "tennis",
}

SELECTION_RESULT_ASSOCIATIONS: dict[SelectionKind, tuple[SelectionResult, ...]] = {
    "over/under": ("over", "under"),
    "home/draw/away": ("home", "draw", "away"),
    "home/away": ("home", "away"),
    "competitor1/competitor2": ("competitor1", "competitor2"),
}
