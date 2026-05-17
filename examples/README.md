# realtimeodds — Python examples

Production-ready snippets that exercise the public SDK. Each script is
self-contained, reads its credentials from the environment, and handles
graceful shutdown on `Ctrl-C` / `SIGTERM`.

## `line_move_alerts.py`

Watches every price tick and logs an alert whenever a selection's price drifts
by more than ±5% (configurable inside the file) from the first quote seen for
that selection in the current session.

Demonstrates:

- `client.odds.find_context(selection_id)` to resolve event + market in one
  O(1) lookup for the alert log line.
- `source:cleared` handling to drop baselines when a bookmaker goes away.
- `disconnected` handling to reset state on session boundaries — the SDK has
  already emptied `client.odds` by the time the event fires.
- Reconnect telemetry (`reconnecting`, `error.fatal`).

```sh
export REALTIMEODDS_URL="wss://api.realtimeodds.xyz/ws"
export REALTIMEODDS_API_KEY="rto_prod_..."
python -m examples.line_move_alerts
```

Run from the repo root (the script is importable as a module).
