# Golden Mind AI Event Bus

The backend exposes `/ws/events` for real-time application events.

Event envelope:
- `event_type`
- `account_id`
- `payload`
- `timestamp`

Examples:
- CONNECTED
- ORDER_SUBMITTED
- ORDER_FILLED
- ORDER_REJECTED
- POSITION_CHANGED
- PNL_CHANGED
- RISK_BLOCKED
- KILL_SWITCH
- ERROR

The bus is intentionally in-process for the current single-server deployment. A production multi-instance deployment should replace it with a durable broker such as Redis Streams or another managed event system.

The WebSocket is an observability/control-plane channel. It does not bypass the execution gate or create trading authority by itself.
