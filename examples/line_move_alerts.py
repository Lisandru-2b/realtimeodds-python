"""Production example — line-move alerts via the realtimeodds Python SDK.

Connects to the public gateway, watches every price tick, and alerts when a
selection's price drifts beyond a configurable threshold from its first seen
quote. Resolves the full event/market context for each alert so the log line
is human-readable.

Usage:
    export REALTIMEODDS_URL="wss://api.realtimeodds.xyz/ws"
    export REALTIMEODDS_API_KEY="rto_prod_..."
    python -m examples.line_move_alerts

Press Ctrl-C to stop gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from collections.abc import Mapping

from realtimeodds import (
    Client,
    DisconnectedEvent,
    ErrorEvent,
    OddsChangedEvent,
    ReconnectingEvent,
    SourceClearedEvent,
    create_client,
)

# Alert when a price moves by more than ±this fraction from the first seen quote.
DRIFT_THRESHOLD = 0.05  # 5%

logger = logging.getLogger("line_move_alerts")


def configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


class LineMoveTracker:
    """First-seen baseline per selection; emit on threshold breach."""

    def __init__(self, client: Client, threshold: float) -> None:
        self._client = client
        self._threshold = threshold
        # selection_id -> baseline price first observed
        self._baseline: dict[str, float] = {}

    def on_odds_changed(self, ev: OddsChangedEvent) -> None:
        sel_id = ev.selection_id
        new_price = ev.quote.price
        baseline = self._baseline.get(sel_id)
        if baseline is None:
            self._baseline[sel_id] = new_price
            return

        drift = (new_price - baseline) / baseline
        if abs(drift) < self._threshold:
            return

        # Threshold breached — resolve the full context for a useful log line.
        ctx = self._client.odds.find_context(sel_id)
        if ctx is None:
            logger.warning("drift on unknown selection %s", sel_id)
            return

        direction = "↓" if drift < 0 else "↑"
        logger.info(
            "%s %s %s: %s %s %.3f → %.3f (%+.1f%%) baseline=%.3f",
            ev.bookmaker,
            ctx.sport_event.name,
            ctx.market.kind,
            ctx.selection.result,
            direction,
            baseline,
            new_price,
            drift * 100,
            baseline,
        )
        # Rebase so we don't spam on continued movement in the same direction.
        self._baseline[sel_id] = new_price

    def on_source_cleared(self, ev: SourceClearedEvent) -> None:
        """Drop baselines for the bookmaker that just went away — otherwise its
        old prices would re-trigger alerts as ghosts when it comes back.
        """
        purged = 0
        # Iterate a copy of the keys because we mutate the dict.
        for sel_id in list(self._baseline.keys()):
            if sel_id.split(":")[1] == ev.bookmaker:
                del self._baseline[sel_id]
                purged += 1
        logger.warning("source cleared: %s (%d baselines dropped)", ev.bookmaker, purged)

    def on_disconnected(self, ev: DisconnectedEvent) -> None:
        # The SDK has already emptied client.odds. Reset baselines too so the
        # next session starts from a clean slate.
        self._baseline.clear()
        logger.warning(
            "disconnected code=%d willReconnect=%s reason=%s",
            ev.code,
            ev.will_reconnect,
            ev.reason or "<empty>",
        )


def env_or_die(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"missing required env var {name}", file=sys.stderr)
        sys.exit(2)
    return value


async def run() -> None:
    configure_logging()
    url = env_or_die("REALTIMEODDS_URL")
    api_key = env_or_die("REALTIMEODDS_API_KEY")

    client = create_client(url=url, api_key=api_key)
    tracker = LineMoveTracker(client, DRIFT_THRESHOLD)

    client.on("connected", lambda _: logger.info("connected, book seeding…"))
    client.on("odds:changed", tracker.on_odds_changed)
    client.on("source:cleared", tracker.on_source_cleared)
    client.on("disconnected", tracker.on_disconnected)
    client.on(
        "reconnecting",
        lambda ev: logger.info("reconnecting attempt=%d delay=%dms", ev.attempt, ev.delay_ms),
    )
    client.on(
        "error",
        lambda ev: (logger.error if ev.fatal else logger.warning)(
            "%s: %s", "fatal" if ev.fatal else "transient", ev.message
        ),
    )

    # Graceful shutdown on SIGINT / SIGTERM.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler — KeyboardInterrupt
            # will bubble out of asyncio.run instead.
            pass

    try:
        await client.connect()
    except Exception as err:
        logger.error("connect failed: %s", err)
        return

    try:
        await stop_event.wait()
    finally:
        logger.info("shutting down")
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
