"""Exponential backoff with jitter — mirrors sb-gateway-client's policy.

Default: 1s → 30s, factor 2, ±30% jitter, unbounded attempts.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Reconnect policy. All fields are optional; defaults match the JS port."""

    initial_delay_ms: int = 1000
    max_delay_ms: int = 30_000
    factor: float = 2.0
    jitter: float = 0.3
    max_attempts: float = math.inf  # `inf` means unbounded


def compute_backoff_delay_ms(attempt: int, policy: ReconnectPolicy) -> int:
    """Compute the next delay in ms for `attempt` (1-based).

    Uses exponential backoff capped by `max_delay_ms`, then applies a uniform
    ±jitter perturbation. Returns 0 if the result would be negative.
    """
    base = min(
        policy.initial_delay_ms * (policy.factor ** (attempt - 1)),
        policy.max_delay_ms,
    )
    jitter_range = base * policy.jitter
    delay = base - jitter_range + random.random() * 2 * jitter_range
    return max(0, int(delay))
