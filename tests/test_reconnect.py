"""Backoff math — exponential growth + jitter behaviour."""

from __future__ import annotations

from realtimeodds import ReconnectPolicy
from realtimeodds._gateway.reconnect import compute_backoff_delay_ms


def test_default_policy_grows_exponentially() -> None:
    policy = ReconnectPolicy(jitter=0.0)  # disable jitter for determinism
    assert compute_backoff_delay_ms(1, policy) == 1000
    assert compute_backoff_delay_ms(2, policy) == 2000
    assert compute_backoff_delay_ms(3, policy) == 4000
    assert compute_backoff_delay_ms(4, policy) == 8000


def test_capped_at_max_delay() -> None:
    policy = ReconnectPolicy(jitter=0.0, max_delay_ms=5000)
    # Without cap, attempt 4 would be 8000ms.
    assert compute_backoff_delay_ms(4, policy) == 5000
    assert compute_backoff_delay_ms(10, policy) == 5000


def test_jitter_stays_within_range() -> None:
    policy = ReconnectPolicy(jitter=0.3)
    base = 1000
    range_low = int(base * 0.7)
    range_high = int(base * 1.3)
    for _ in range(50):
        d = compute_backoff_delay_ms(1, policy)
        assert range_low - 1 <= d <= range_high + 1


def test_zero_attempt_count_is_handled() -> None:
    policy = ReconnectPolicy(jitter=0.0, initial_delay_ms=1000)
    # Attempt 1 returns initial_delay_ms (factor**0 = 1).
    assert compute_backoff_delay_ms(1, policy) == 1000
