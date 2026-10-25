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
5. `restart_live_session(session_id)`: run a session again after it stopped, crashed, or failed.
   See "Restarting a session".
6. `copy_live_session(session_id)`: the dashboard's "New session": a new draft with the same form,
   to review or change before starting it.
7. `update_live_session_notes(session_id, title, description)` and
   `delete_live_session(session_id)` (refused while the session runs or is open in a dashboard Live
   tab; it never touches the exchange account).

Live and paper sessions do not use research credits.

## Restarting a session

When the user wants a session restarted, run again, or brought back up, use
`restart_live_session(session_id)`. It creates a new session with the same mode (paper, or live
with real funds), exchange, API key, routes, data routes, and configuration, including leverage,
margin mode, and for paper sessions balance and fee, and starts it in one step. The new session
keeps the old title unless you pass `title`; the old session stays in the history unchanged.

Never rebuild a session with `create_live_draft` to restart it. A new draft takes the saved
defaults for its key or paper exchange, not the settings the session ran with, so its leverage can
silently differ.

A restart is refused:

- while the session is still running (`session_active`): it never stops a session. Stop it only
  if the user asks (see "What stopping does"), then restart it;
- when another session already runs the same routes on the same key or paper exchange
  (`routes_already_running`): that one may be the restart already;
- for a draft (`is_draft`): start it with `start_live_session`.

If the session did not store all of its money settings (sessions that ran on older Jesse
versions), the restart saves the copy as a draft and does not start it (`settings_not_copied`).
The message lists the values the copy would use and where each came from. Confirm them with the
user, change them with `update_live_draft(config={"exchange": {...}})` if needed, then start it.

## Where a session's settings come from

Draft, copy, and restart results include `config_source`: where the leverage and margin mode (and,
for paper sessions, the balance and fee) came from:

- `explicit`: this call's `config`;
- `stored`: the draft already had it; `copied`: the session it was copied or restarted from;
- `saved_default`: the dashboard's saved settings for that API key or paper exchange;
- `exchange_default`: the exchange's listed fee;
- `hard_default`: Jesse's built-in value (5x cross leverage, 10,000 balance), because nothing
  was saved. `config_warnings` then flags the leverage or fee; ask the user before starting.

`create_live_draft` also returns `earlier_session` when a started session already ran (or is
running) the same routes in the same mode on the same key or paper exchange, with any money
setting that differs. Usually the user means to restart that session: tell them, and use
`restart_live_session` unless they want a separate new session. A running one means a second
session would trade the same symbols twice.

## Reading sessions

Use the session results tools: `get_live_sessions()` lists started sessions (drafts are not
listed), and `get_session_results("live", session_id)` returns the summary (status, form, error,
counts), then pages of `closed_trades`, `orders`, `equity_curve`, `logs`, and `error_logs`, with the
session's saved credential values redacted. For a period across sessions ("my trades of the last 7
days"), use `get_live_trades` / `get_live_orders` (Jesse's records, not the exchange account's
history; live only unless `mode` says otherwise). See `jesse://session_analysis`.

Every one of these, like the tools above, returns the session's dashboard link: `dashboard_url` on
a single session's response and on each row of `get_live_sessions()`, and
`session_dashboard_url_template` (replace `{session_id}`) on the history pages. When the user asks
for a session, or for its URL, answer with that link first; the session ID alone does not help
them. Opening it loads the session into a dashboard Live tab.

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

- Create, start, restart, stop, or delete sessions only when the user asks for that action. Before
  starting, state whether it is a paper or a real-money live session, on which exchange and key,
  and its leverage.
- Restart with `restart_live_session`, never with a new draft.
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

# Later, after it stopped or crashed: run it again with the same settings.
again = restart_live_session(draft["session_id"])
get_session_results("live", again["session_id"])
```
