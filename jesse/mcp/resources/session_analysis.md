# Session Results and Temporary Analysis

Jesse stores the results of every backtest, optimization, Monte Carlo run, rule significance
test, and live/paper session. These tools read them on the machine running Jesse, so they
work the same when you run on another computer or Jesse runs in Docker.

## Reading results: `get_session_results`

```
get_session_results(session_type="backtest", session_id="<uuid>")                    # summary
get_session_results(session_type="backtest", session_id="<uuid>", section="trades", offset=0, limit=50)
```

- Always read `section="summary"` first. It returns `session_status`, the run's form (routes,
  dates, options), the stored metrics or results, the error message and traceback tail when
  the run failed, and what each other section contains (counts, curve lengths, log size).
- `status_note` explains unfinished states (`running`, `draft`, `stopped`, `cancelled`,
  `terminated`). Results of those runs may be missing or partial; say so instead of
  treating them as final.
- Sections per `session_type`:

| session_type | sections besides `summary` |
|---|---|
| `backtest` | `trades`, `equity_curve`, `hyperparameters`, `logs` |
| `optimization` | `best_trials` (best first; params + full training/testing metrics), `objective_curve`, `logs` |
| `monte_carlo` | `confidence_analysis`, `scenario_metrics` (original + every scenario), `equity_curves` (Portfolio curve of the original and each scenario), `logs` |
| `significance_test` | — (summary holds all stored results: p_value, observed_mean, annualized_return, n_simulations, n_observations) |
| `live` | `closed_trades`, `orders`, `equity_curve` (per-minute equity snapshots), `logs` (info), `error_logs` |

- Pages hold at most `limit` items (1-500, default 50) and at most 128 KiB of JSON.
  Continue from `next_offset` while `has_more` is true. For equity curves an item is a point
  of each series. For logs, `offset` counts back from the newest entry and each page is
  oldest first.
- Values are exactly what Jesse stored; NaN and infinite numbers are `null`. Do not invent
  or estimate fields that are not there.
- Existing list tools (`get_backtest_sessions`, `get_optimization_sessions`,
  `get_monte_carlo_sessions`, `get_significance_test_sessions`) and `get_live_sessions`
  find session IDs. `get_backtest_session` and the other `get_*_session` tools return the
  raw dashboard record, including every trade and curve point; prefer
  `get_session_results` for reading results.

Live and paper sessions:
- Readable only when the live trading plugin is installed and enabled
  (`live_plugin_unavailable` otherwise).
- Reading never starts or stops a session. Managing sessions (drafts, start, stop, delete) has
  its own tools and rules: see `jesse://live_trading`.
- Exact occurrences of the saved API key, secret, extra fields (such as a passphrase), and
  notification credential values (6+ characters) of the keys the session uses are replaced
  with `[redacted]` in responses and analysis snapshots. This is text matching: anything
  else a strategy logged is returned as stored, so never repeat credential-looking text.

## Live/paper trades and orders by date: `get_live_trades`, `get_live_orders`

For questions about a period rather than one session ("my trades of the last 3 days", "what
did I trade this week on Bybit"), read across all live/paper sessions by date window:

```
get_live_trades(recent_days=3)                                   # closed trades, newest first
get_live_trades(start="2026-09-01T00:00:00Z", end="2026-09-08T00:00:00Z", symbol="BTC-USDT")
get_live_orders(recent_days=7, time_field="executed_at", status="EXECUTED")
```

- The data is Jesse's own records of its sessions, not the exchange account's history.
  Trades made outside Jesse or while no session ran are not there; nothing contacts the
  exchange. Say so when it matters.
- Window: nothing = the last 7 days; `recent_days` 1-366; or `start` (+ optional `end`,
  default now) as RFC 3339 date-times with an offset (`...Z` or `...+03:00`; date-only or
  offset-less values are refused as ambiguous). Bounds are UTC, start inclusive, end
  exclusive. The response's `range` holds the exact bounds used; a relative window is
  resolved once.
- Paging: call the tool again with exactly the arguments in `next_page` (window, mode,
  filters, order, limit, and a `cursor`). A cursor with any other window, mode, filter, or
  order is refused (`invalid_cursor`), so a later page can never widen the selection. Each
  page is one consistent database view and continues after the last record's (time, id), so
  records added or removed before it never shift later pages; records changed between calls
  (for example a trade the plugin reconciles later) can still appear or disappear. Pages
  stop at `limit` records, at 128 KiB (`truncated_by_size`), and for trades before loading
  more than 20,000 executed orders (`truncated_by_orders`). A trade with more than 10,000
  executed orders is refused (`too_many_orders`) rather than computed from part of them.
- `mode` defaults to `"live"` (real money only); `"paper"` or `"all"` only when the user wants
  paper results. Never mix paper results into real performance. `exchange`/`symbol` match
  exactly as stored; `session_id` limits to one session (`mode_mismatch` if it is of the other
  mode).
- Trades are CLOSED trades selected by `closed_at`. Open positions are never included;
  `open_trades_not_included` counts them. `pnl` is the dashboard's value (price difference ×
  qty minus the fees Jesse recorded on the trade's executed orders); `orders_without_fee > 0`
  means fees are incomplete. There is no account balance or equity in these results: do not
  present sums of trade pnl as account performance or balance.
- Orders keep their stored `status`, `executed_at`, `canceled_at`; `time_field` chooses
  creation (`created_at`, default) or execution (`executed_at`) time; `counts_by_status`
  covers the whole selection.
- `total` counts every match in that page's view; `all_records_returned` is true only when
  the first page holds them all. Never compute totals, win rates, or other statistics from a
  partial page or by stitching pages together: use `run_analysis` with a dataset input
  (below), which gets every record from one consistent view.
- `pnl` is in each symbol's quote currency (`BTC-USDT` → USDT, `ETH-BTC` → BTC). Never add
  pnl across quote currencies or across live and paper trades, and never convert between
  currencies; a symbol not in `BASE-QUOTE` form has no known currency. A trade can have
  `pnl: null` (no executed exit or entry orders): report how many, and do not compute a total
  or win rate for a group that has any (a sum would skip them; a win rate would count them as
  losses).
- `total: 0` means Jesse recorded no closed trades (or orders) in that window and scope: tell
  the user exactly that, with the range, and mention open trades if
  `open_trades_not_included` > 0. Do not run an analysis on an empty selection.

## Temporary analysis: `run_analysis`

Use it when the user asks you to analyze, compare, or chart session results, or when a
question needs statistics over more rows than you should page through. The request to
analyze or chart authorizes this temporary analysis only. It is **not** a request for a
research script: never create, edit, or run files in `research_scripts/` for it (see
`jesse://research_scripts` for when scripts are allowed).

```
run_analysis(
    code="...",
    inputs=[
        {"session_type": "backtest", "session_id": "<uuid A>", "name": "base"},
        {"session_type": "backtest", "session_id": "<uuid B>", "name": "tuned"},
    ],
    timeout_minutes=5,
)
→ {"status": "success", "job": {"id": "<job_id>", "status": "running", "inputs": [...], ...}}
get_analysis_job(job_id="<job_id>")          # status, artifacts, console output
get_analysis_artifact(job_id="<job_id>", path="equity.png")   # the chart as an image
```

An input can also be the live/paper history of a date window across sessions, with the same
window and filters as `get_live_trades` / `get_live_orders`:

```
run_analysis(code="...", inputs=[
    {"dataset": "live_trades", "name": "trades", "recent_days": 7},
    {"dataset": "live_orders", "name": "orders", "start": "2026-09-01T00:00:00Z",
     "end": "2026-09-08T00:00:00Z", "mode": "all", "symbol": "BTC-USDT"},
])
```

Each dataset input, and each `live` session input, is read from one consistent database view
(its counts, rows, and orders agree even while sessions write); separate inputs are separate
views, taken one after the other. A live session snapshot reports a session left marked running
without a worker as stopped, like the dashboard, without writing that back. Other session types
are stored results of finished runs and are read as stored. The snapshot holds every matching record, oldest first, or the run is refused with
`too_many_records` (more than 100,000 trades or orders in one input; split the period into
several inputs or add filters); it is never silently cut. Unknown fields (such as a
misspelled filter) are refused. The window is resolved when the run starts; the job's
`inputs` (the manifest) show its exact `range`, `filters`, and `count`: report those.

What happens:
1. Jesse writes each input's complete data to `inputs/<name>.json` in a new
   workspace, `storage/mcp/analysis/<job_id>/` on the Jesse machine, plus
   `inputs/manifest.json` (name, file, session_type, session_id, session_status, title,
   size_bytes; for datasets: dataset, range, filters, count, size_bytes).
   You never paste result arrays into the code.
2. Your code is saved as `analysis.py` and run with Jesse's Python (numpy, pandas,
   matplotlib, and the other packages installed with Jesse) from the workspace folder,
   without a shell. `MPLBACKEND=Agg` is set.
3. Write every chart or table to `output/` (sub-folders are fine). Only files under
   `output/` can be fetched.

Rules for analysis code:
- Only read `inputs/` and write `output/`. Never read `.env` or credentials, place orders,
  contact exchanges, or install packages.
- Do not start backtests, optimizations, or other Jesse runs from analysis code; use the
  run tools for new results, then analyze their stored results.
- Print short numeric findings (they appear in `get_analysis_job` output); keep the
  explanation in your reply.
- Images: PNG (recommended), JPEG, GIF, or WebP, at most 3 MiB and 8000 px per side, e.g.
  `fig.savefig("output/equity.png", dpi=110)` with a figure around 10x5 inches. Close
  figures after saving.
- Snapshots are complete or refused: a live session over its row caps (`too_many_records`)
  or any input over 64 MiB (`too_large`) stops the run before it starts. Analyze a long live
  history with date-window dataset inputs instead.
- Limits: code 256 KiB; up to 10 inputs, 64 MiB each and 256 MiB together; 1-30 minutes
  (default 5); 2 analysis jobs at once; console output kept up to 5 MiB.
- A failed job's output ends with the Python traceback. Fix the code and run a new job.

Lifetime: cleanup runs whenever a new analysis starts (there is no timer). It deletes
workspaces whose job finished more than 24 hours earlier (the job's `expires_at`), then the
oldest finished ones while more than 50 or 2 GiB are kept. So fetch the artifacts you need
soon after a job finishes; a workspace can disappear at any later `run_analysis`. Jobs the
running Jesse process is still running are never deleted. After a Jesse crash or restart,
a job from before counts as finished (`interrupted`), even if its process is still running.
`delete_analysis_job` removes a finished job's workspace immediately; `cancel_analysis_job`
stops a running one.

If your client cancels or gives up on a `run_analysis` call, the job may still have started
on the Jesse host; the cancellation reply does not say. List the newest jobs with
`get_analysis_job()` before running it again, and cancel a duplicate you do not need. A job
is only stopped by `cancel_analysis_job`, its timeout, or a Jesse shutdown.

Security: analysis code is ordinary Python running as the Jesse user. It is **not
sandboxed**: it can read any file that user can, the database and saved credentials, and
use the network. The workspace and artifact checks only decide which files Jesse returns.

### Snapshot layout (`inputs/<name>.json`)

Every snapshot has `"summary"` (the same object `get_session_results` returns for
`section="summary"`), plus:

| session_type | keys |
|---|---|
| `backtest` | `metrics` (dict), `trades` (list: `id`, `symbol`, `type`, `entry_price`, `exit_price`, `qty`, `opened_at`/`closed_at` in ms, `fee`, `size`, `PNL`, `PNL_percentage`, `holding_period` in seconds, `orders`), `equity_curve` (list of series `{"name", "color", "data": [{"time": <unix seconds>, "value"}]}`; "Portfolio" first, benchmark series when enabled), `hyperparameters` (list of `[name, value]`) |
| `optimization` | `best_trials` (list: `rank`, `trial`, `params`, `fitness`, `dna`, `training_metrics`, `testing_metrics`, `objective_metric`), `objective_curve` |
| `monte_carlo` | `pipelines`: `{"candles": results or null, "trades": results or null}`; each results object has `original` (the unmodified backtest), `scenarios` (list), `confidence_analysis`, `num_scenarios`, `total_requested` |
| `significance_test` | summary only (`summary.results`) |
| `live` | `closed_trades` (oldest first: `id`, `symbol`, `type`, `entry_price`, `exit_price`, `qty`, `pnl`, `pnl_percentage`, `opened_at`, `closed_at`, `status`, `fee`, `leverage`, ...), `orders`, `equity_curve` (`[{"time": <ms>, "equity", "currency"}]`), `complete` (always true: a session with more than 100,000 trades, 200,000 orders, or 600,000 equity points is refused with `too_many_records`, never cut) |

Dataset inputs have no `summary`; their keys:

| dataset | keys |
|---|---|
| `live_trades` | `dataset`, `source`, `range` (`start`, `end`, `start_ms`, `end_ms`, `source`, `recent_days`), `filters`, `order`, `note`, `open_trades_not_included`, `trades` (oldest first by `closed_at`: the fields listed for `get_live_trades`), `sessions` (by ID: `exists`, `title`, `session_mode`, `exchange`, `status`, ...), `count`, `complete` (always true) |
| `live_orders` | the same header with `counts_by_status`, `orders` (oldest first by the chosen `time_field`), `sessions`, `count`, `complete` |

Inspect unfamiliar keys before relying on them, for example
`print(list(data["pipelines"]["candles"]["scenarios"][0]))`.

Example (compare two backtests' equity curves):

```python
import json
import matplotlib.pyplot as plt
import pandas as pd

fig, ax = plt.subplots(figsize=(10, 5))
for name in ("base", "tuned"):
    data = json.load(open(f"inputs/{name}.json"))
    portfolio = next(s for s in data["equity_curve"] if s["name"] == "Portfolio")
    curve = pd.DataFrame(portfolio["data"])
    curve["time"] = pd.to_datetime(curve["time"], unit="s")
    ax.plot(curve["time"], curve["value"], label=f'{name} ({data["metrics"]["net_profit_percentage"]:.1f}%)')
    print(name, "max drawdown", data["metrics"]["max_drawdown"])
ax.set_title("Equity")
ax.legend()
fig.savefig("output/equity.png", dpi=110, bbox_inches="tight")
plt.close(fig)
```

### Workflow: "analyze my trades of the last 7 days"

1. Discover: `get_live_trades(recent_days=7, limit=20)` (add `mode`, `exchange`, `symbol`,
   `session_id` only as the user asked). Note `range`, `filters`, `total`,
   `open_trades_not_included`, and whether `sessions` include paper ones (only with
   `mode="all"`/`"paper"`).
   - `total` is 0: reply that Jesse recorded no closed trades for that selection between
     `range.start` and `range.end` (mention open trades if counted, and that paper sessions
     were excluded unless asked). Stop there: run no analysis.
   - Otherwise continue; answer from the page alone only for a simple question when
     `all_records_returned` is true and every returned trade has a `pnl`.
2. Analyze the same selection. Build the input from the discovery response: `start` and `end`
   from `range`, and every entry of `filters` except `session_modes` whose value is not null
   (`mode`, and `exchange`, `symbol`, `session_id` when set; for `live_orders` also
   `time_field` and `status`). Never add or drop a filter between the two steps.

```
run_analysis(code=CODE, inputs=[{"dataset": "live_trades", "name": "trades",
                                 "start": "<range.start>", "end": "<range.end>",
                                 "mode": "<filters.mode>", "symbol": "<filters.symbol, if not null>"}])
```

   The analysis reads a new database view, so it covers the same selection, not necessarily
   the same rows: trades recorded or reconciled in between can change it. Report the job's
   `inputs[0]` (the snapshot manifest: `count`, `range`, `filters`), not the discovery page's
   `total`.

```python
import itertools
import json
import math
import re
from datetime import datetime, timezone

import matplotlib.pyplot as plt

data = json.load(open("inputs/trades.json"))
print("range", data["range"]["start"], "->", data["range"]["end"], "| trades", data["count"],
      "| open trades not included", data["open_trades_not_included"],
      "| filters", json.dumps(data["filters"], sort_keys=True))


def quote_of(symbol):
    # Jesse symbols are BASE-QUOTE, and pnl (price difference x qty) is in the quote currency.
    # Any other form has no known currency: its trades are listed, never added to others.
    parts = symbol.split("-") if isinstance(symbol, str) else []
    return parts[1] if len(parts) == 2 and parts[0] and parts[1] else None


# Different currencies (USDT, BTC, USD) and live vs paper results are never added together.
groups = {}
for trade in sorted(data["trades"], key=lambda t: (t["closed_at"], t["id"])):
    groups.setdefault((trade["session_mode"], quote_of(trade["symbol"])), []).append(trade)
if not groups:
    print("no closed trades in this window")

for (mode, quote), trades in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1] or "")):
    unknown = sum(1 for t in trades if t["pnl"] is None)
    missing_fees = sum(1 for t in trades if t["orders_without_fee"] > 0)
    print(f"group mode={mode} quote={quote or 'unknown'} trades={len(trades)} "
          f"unknown_pnl={unknown} missing_fee_trades={missing_fees}")
    if quote is None:
        print("  not computed: the symbol is not BASE-QUOTE, so the pnl currency is unknown")
        continue
    if unknown:
        # A trade without executed exit (or entry) orders has no pnl; a total without it would
        # be wrong, and counting it as a loss would be too.
        print(f"  not computed: {unknown} of {len(trades)} trades have no pnl")
        continue
    pnls = [t["pnl"] for t in trades]
    wins = sum(1 for value in pnls if value > 0)
    # Full precision (no rounding: BTC amounts are small); math.fsum avoids float drift.
    print(f"  net_closed_trade_pnl={math.fsum(pnls)!r} {quote} wins={wins}/{len(trades)}")
    times = [datetime.fromtimestamp(t["closed_at"] / 1000, timezone.utc) for t in trades]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.step(times, list(itertools.accumulate(pnls)), where="post")
    ax.set_title(f"Cumulative pnl of closed {mode} trades in {quote} (Jesse records, not account equity)")
    ax.set_ylabel(quote)
    path = "output/cumulative_pnl_" + re.sub(r"[^A-Za-z0-9]+", "_", f"{mode}_{quote}") + ".png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  chart {path}")
```

3. `get_analysis_job(job_id)` until it finishes, then `get_analysis_artifact(job_id, path)` for
   each printed chart. In the reply, give each group (mode, quote currency) separately with the
   manifest's range, count, and filters; say that the figures are closed trades Jesse recorded
   (not open positions, the account balance, or equity); name groups that were not computed and
   why (trades without pnl, unknown currency); and mention trades with missing fees.
