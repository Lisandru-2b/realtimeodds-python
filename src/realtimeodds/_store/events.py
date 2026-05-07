"""Internal store event payload shapes (mirror sb-odds-store)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .._entities import SportEvent
from .._types import SelectionId, SportEventId


@dataclass(frozen=True, slots=True)
class SportEventUpsertedPayload:
    sport_event: SportEvent
    is_new: bool


@dataclass(frozen=True, slots=True)
class SportEventRemovedPayload:
    sport_event_id: SportEventId


@dataclass(frozen=True, slots=True)
class PricesUpdatedPayload:
    sport_event_id: SportEventId
    prices: Mapping[SelectionId, float]
