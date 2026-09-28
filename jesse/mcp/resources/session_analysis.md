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
- Reading never starts, stops, or changes a session. There is no MCP tool to start or stop
  live trading; tell the user to use the dashboard.
- Exact occurrences of the saved API key, secret, extra fields (such as a passphrase), and
  notification credential values (6+ characters) of the keys the session uses are replaced
  with `[redacted]` in responses and analysis snapshots. This is text matching: anything
  else a strategy logged is returned as stored, so never repeat credential-looking text.

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

What happens:
1. Jesse writes each input's complete stored results to `inputs/<name>.json` in a new
   workspace, `storage/mcp/analysis/<job_id>/` on the Jesse machine, plus
   `inputs/manifest.json` (name, file, session_type, session_id, session_status, title,
   size_bytes).
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
| `live` | `closed_trades` (oldest first: `id`, `symbol`, `type`, `entry_price`, `exit_price`, `qty`, `pnl`, `pnl_percentage`, `opened_at`, `closed_at`, `status`, `fee`, `leverage`, ...), `orders`, `equity_curve` (`[{"time": <ms>, "equity", "currency"}]`), `truncated` (flags when row caps were hit) |

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
