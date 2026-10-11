# Live and Paper Trading Sessions

The live/paper tools manage the same sessions as the dashboard's Live page. They need the Jesse
live trading plugin; without it every tool answers `live_plugin_unavailable`.

## Paper vs live

Every session is one or the other, and the tools always say which (`mode`, `trading`):

- **Paper** (`paper_mode=true`): orders are simulated against live market data. No real funds and
  no exchange key; you choose the `exchange`. Balance, fee, and market type in the session config
  are simulation values.
- **Live** (`paper_mode=false`): REAL orders with real funds, through a saved exchange API key
  (`exchange_api_key_id` from `get_exchange_api_keys()`). The session trades on that key's
  exchange and uses the venue's own balance and market type.

Keys are referenced by ID only; no tool reads or returns a stored secret. Store keys with the
credential tools (`jesse://credentials`).

## Lifecycle

1. `create_live_draft(paper_mode, routes, ...)`: a draft, like a new dashboard Live tab. Nothing
   runs. The draft gets its own configuration, resolved like the dashboard does from the saved
   defaults for that paper exchange or key; `config` overrides apply to this draft only and saved
   settings never change.
2. `update_live_draft(session_id, ...)`: change a draft before it starts. Started sessions are
   fixed.
3. `start_live_session(session_id)`: the dashboard's Start button, with the same request. The form
   is validated again; then the session itself checks the license and plan (allowed exchanges,
   routes, timeframes, and paper trading), connects to the exchange, and loads warm-up candles.
   Follow it with `get_session_results("live", session_id)` until `session_status` is `running`;
   a license or plan refusal, or any other failure, shows up there as `error`.
4. `stop_live_session(session_id)`: the dashboard's Stop button. See "What stopping does".
5. `copy_live_session(session_id)`: the dashboard's "New session": a new draft with the same form.
   To run a finished or failed session again, copy it and start the copy.
6. `update_live_session_notes(session_id, title, description)` and
   `delete_live_session(session_id)` (refused while the session runs or is open in a dashboard Live
   tab; it never touches the exchange account).

Live and paper sessions do not use research credits.

## Reading sessions

Use the session results tools: `get_live_sessions()` lists started sessions (drafts are not
listed), and `get_session_results("live", session_id)` returns the summary (status, form, error,
counts), then pages of `closed_trades`, `orders`, `equity_curve`, `logs`, and `error_logs`, with the
session's saved credential values redacted. For a period across sessions ("my trades of the last 7
days"), use `get_live_trades` / `get_live_orders` (Jesse's records, not the exchange account's
history; live only unless `mode` says otherwise). See `jesse://session_analysis`.

## What stopping does

Stopping asks the session process to end; a running session notices within about a second, one
still starting once its startup checks (such as the license check) finish. What happens to open
orders and positions is decided by the live plugin:

- A **paper** session, or a **live** session whose `persistency` setting is off, cancels the open
  orders of its routes' symbols and closes their open positions with market orders while ending.
- A **live** session with `persistency` on leaves its orders and positions on the exchange so a
  later session can continue them.

The stop request does not wait for this. Report exactly this to the user (never "positions are
closed" for a persistent live session), and confirm the outcome with the session's summary,
orders, and logs.

## Rules for assistants

- Create, start, stop, or delete sessions only when the user asks for that action. Before starting,
  state whether it is a paper or a real-money live session, on which exchange and key.
- There is no order placement or manual position tool. Strategies trade; you manage sessions.
- A cancelled or timed-out call may still have taken effect: check with
  `get_session_results("live", session_id)` or `get_live_sessions()` before retrying a start or
  stop.

## Example

```python
draft = create_live_draft(
    paper_mode=True,
    exchange="Bybit USDT Perpetual",
    routes='[{"strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}]',
    config='{"exchange": {"balance": 5000}}',
)
start_live_session(draft["session_id"])          # only when the user asks
get_session_results("live", draft["session_id"])  # until session_status is "running"
```
