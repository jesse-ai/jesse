# Monte Carlo Simulation via MCP

Monte Carlo (MC) estimates the distribution of strategy outcomes by re-running
the strategy across many resampled variants of the data. It answers questions
like "how lucky was this backtest?" and "what does the downside tail look like?"

Jesse supports two MC modes:

| Mode | What it resamples | When to use |
|---|---|---|
| **Candles** (default) | The underlying OHLCV series via a bootstrap pipeline | The main MC mode. Tests whether the strategy's edge survives plausible alternative price paths. |
| **Trades** (opt-in only) | The order of the executed trade sequence | Diagnostic for trade-sequencing / drawdown-path risk. Run ONLY when the user explicitly asks for it. |

By default the MCP runs **candles-only with 200 scenarios**, which is the
informative setting for most strategies. Increase `num_scenarios` to 500–1000
when you need tighter tail estimates.

**Do NOT enable `run_trades` on a generic "run Monte Carlo" / "check for
overfitting" request.** It doubles the runtime, adds almost no extra signal
for the overfit question, and only carries information for the *drawdown-path*
question (see "Interpreting trades MC" below). Enable `run_trades=True` only
when the user says things like "shuffle trade order", "trade-sequencing
risk", "trades resampling", or explicitly asks for both modes.

## When to use

- A backtest produced strong results — run candles MC to check whether the
  edge is robust to alternative price paths.
- A user asks "is this strategy lucky / robust / overfit?" — MC is the
  primary tool for that question.
- Comparing two strategy variants on the same data — MC's `worst_5`
  percentile is a much better selection criterion than the original sharpe.

## Interpreting summary_metrics

**Important:** the candles MC and trades MC answer DIFFERENT questions
and must be interpreted differently. The four-number overfit rule below
is for candles MC only — trades MC has a much narrower scope, see
"Interpreting trades MC" below.

The primary question candles MC answers is **"is the strategy overfit?"**,
and the answer comes from comparing the `original` backtest against the
distribution of MC scenarios. Each metric (sharpe_ratio, max_drawdown,
net_profit_percentage, win_rate, calmar_ratio, etc.) comes back as four
numbers:

| Field | Meaning |
|---|---|
| `original` | The metric from the unaltered strategy run |
| `best_5` | 95th-percentile MC scenario (the lucky tail) |
| `median` | 50th-percentile MC scenario |
| `worst_5` | 5th-percentile MC scenario (the unlucky tail) |

### Overfit detection (for higher-is-better metrics)

The headline rule, ordered from worst to best, on the sharpe_ratio (and
analogously on net_profit, win_rate, calmar):

| Where `original` falls | Verdict |
|---|---|
| `original > best_5` | **Overfit / suspect.** The real backtest beat 95% of resampled paths — it sits in the luckiest tail. Do not trust the result. |
| `best_5 >= original > median` | Borderline. Above median MC but inside the plausible range. Better than overfit, still not great. |
| `original ≈ median` | **Good.** The backtest is representative of typical MC outcomes — no luck premium. |
| `original < median` | **Fantastic.** The real result is conservative vs what MC suggests the strategy can do — strong evidence it's not overfit. |

The intuition: if the MC scenarios are believable alternatives to what
actually happened, then a `best_5`-beating `original` means the backtest
was an exceptional run, which is exactly the signature of overfitting.
An `original` near or below `median` means the strategy held up against
the typical resampled path — that's the kind of result you can trust.

### Downside tail (separate question)

`worst_5` is not about overfit — it's about **"how bad does it get?"**:

- For sharpe / profit / win_rate / calmar: `worst_5` is the 5th-percentile
  outcome. If it's still acceptable (e.g. `worst_5_sharpe > 0`), the
  strategy survives the unlucky tail.
- For max_drawdown the comparison flips — `worst_5_max_drawdown` is the
  worst-case loss and should not exceed what the user can stomach.

### What to always report (candles MC)

For the key metrics (`sharpe_ratio` first, then `net_profit_percentage`,
`max_drawdown`, `calmar_ratio`), report all four numbers plus the verdict
from the overfit table above. Don't conflate "not overfit" with "robust on
the downside" — they're independent questions.

### Interpreting trades MC

Trades MC only **shuffles the order** of the already-executed trades —
it does not change which trades happen, their P&Ls, win rate, total
return, or sharpe. So:

- `total_return`, `win_rate`, and any non-path-dependent metric are
  **invariant under shuffling** and carry no information. Do NOT report
  their percentile bands or run the overfit comparison on them — it's
  noise. (You may see slight numerical variation in `sharpe_ratio`
  across resamples from how it's calculated on a re-ordered timeline,
  but that variation is also not meaningful and should not be reported
  as an overfit signal.)
- The ONLY metric trades MC informs is **`max_drawdown`** (and by
  extension `calmar_ratio`, which is derived from drawdown). Different
  trade orderings stack losses differently → different drawdown paths.
- The question trades MC answers is: **"how bad could the equity-curve
  drawdown have been if the wins and losses had arrived in a different
  order?"** That's a drawdown-path / sequencing-risk question, not an
  overfit question.

What to report for trades MC: `max_drawdown` percentiles only
(`original`, `worst_5`, `median`, `best_5`). Skip everything else.
If the user asks "is this strategy overfit?", trades MC does NOT
answer that — point them to the candles MC results.

## Tool reference

### create_monte_carlo_draft()

Stages a draft you can then run.

- `exchange` (default `"Binance Perpetual Futures"`)
- `routes` — JSON string array of route objects
- `data_routes` — JSON string array (default `"[]"`)
- `start_date`, `finish_date` — `YYYY-MM-DD`
- `num_scenarios` — int (default **200**, recommend 200–1000)
- `run_trades` — bool (default **False**)
- `run_candles` — bool (default **True**)
- `fast_mode` — bool (default False; skip charts/heavy outputs)
- `cpu_cores` — int (default: `cpu_count - 1`, capped at 4)
- `pipeline_type` — str (default `"moving_block_bootstrap"`)
- `pipeline_params` — optional JSON object string
- `title`, `description`, `strategy_summary`, `hypothesis`, `rationale` —
  optional notes metadata; auto-generated if omitted

Returns: `{ "status": "success", "session_id": "<uuid>", ... }`

### update_monte_carlo_draft(session_id, state)

Replace the whole `state` on an existing draft. Use the same
read-modify-write pattern as `update_backtest_draft`.

### update_monte_carlo_notes(session_id, title?, description?, strategy_codes?)

Update notes after the simulation finishes — typical use is recording the
conclusion.

### get_monte_carlo_session(session_id)

Fetch full details. Both `trades_session` and `candles_session` carry their
own `status`, `num_scenarios`, `completed_scenarios`, and `summary_metrics`.
The outer `status` reflects overall progress.

```json
{
  "data": {
    "session": {
      "id": "<uuid>",
      "status": "finished",
      "candles_session": {
        "status": "finished",
        "num_scenarios": 200,
        "completed_scenarios": 200,
        "pipeline_type": "moving_block_bootstrap",
        "summary_metrics": [
          {"metric": "sharpe_ratio", "original": 1.8,
           "worst_5": 0.6, "median": 1.4, "best_5": 2.2}
        ]
      },
      "trades_session": null
    }
  },
  "error": null,
  "message": "Monte Carlo session retrieved successfully"
}
```

### get_monte_carlo_sessions(limit?, offset?, title_search?, status_filter?, date_filter?)

List sessions (most recent first). `status_filter` values: `draft`,
`running`, `finished`, `stopped`, `terminated`. `date_filter` values:
`7_days`, `30_days`, `90_days`.

### get_monte_carlo_equity_curves(session_id)

Fetch the per-scenario Portfolio equity curves. Use this when the agent
needs to compute custom statistics across scenarios or describe dispersion
visually.

```json
{
  "status": "success",
  "trades":   { "original": {...}, "scenarios": [{...}, ...] },
  "candles":  { "original": {...}, "scenarios": [{...}, ...] }
}
```

### get_monte_carlo_logs(session_id)

Fetch the log file content. Useful when `status == "stopped"` /
`"terminated"` to find the underlying error, or to inspect scenario-by-scenario
progress in a long run.

### run_monte_carlo(session_id)

Fire-and-poll. Returns `{ "status": "started", "session_id": ... }` when the
server accepts (HTTP 202). Then poll `get_monte_carlo_session` until
`status == "finished"` (or `stopped` / `terminated`). **See "Polling
discipline" below — keep polling until a terminal status is reached, no
exceptions.**

## Polling discipline

Monte Carlo runs are slow — candles MC re-runs the full strategy on
`num_scenarios` resampled price series. A 200-scenario candles MC on a
one-year window typically takes minutes; longer windows or more scenarios
can take **30+ minutes or hours**. Polling has two requirements:

1. **Keep polling until terminal status.** Terminal statuses are
   `finished`, `stopped`, `terminated`. Do NOT stop polling because
   "it's taking a while" or "progress hasn't moved" — candles MC often
   processes all scenarios in a batch and only updates
   `completed_scenarios` at the end. Reporting "done" before
   `status` is terminal is a hard error.
2. **Adapt the poll interval to expected remaining time.** Pounding the
   server every second on a 30-minute run wastes turns. Use the
   adaptive schedule below.

Adaptive polling schedule (when `status == "running"`):

| Elapsed since fire | Poll interval |
|---|---|
| 0 – 1 min | every 5 s |
| 1 – 5 min | every 15 s |
| 5 – 15 min | every 30 s |
| 15 – 60 min | every 60 s |
| > 1 h | every 2–3 min |

Refinements:
- If `candles_session.completed_scenarios > 0`, you can estimate ETA as
  `elapsed * (num_scenarios / completed_scenarios)`. Set the next poll
  to roughly `min(remaining_eta / 5, max_interval)`.
- If `completed_scenarios` is still 0 after several minutes, that's
  expected for candles MC — it batches across `cpu_cores` workers and
  reports only at the end. Don't conclude it's stuck.
- If polling exceeds 2 hours with no terminal status AND no scenario
  progress, surface this to the user with the session_id and ask
  whether to keep waiting, cancel, or terminate.

Status semantics for polling:
- `running` → keep polling
- `finished` → done, read `summary_metrics`
- `stopped` → run failed; fetch `get_monte_carlo_logs(sid)` for the
  underlying error and report it to the user
- `terminated` → user-initiated stop; report the partial state, do not
  retry without the user's say-so

### resume_monte_carlo(session_id)

Re-fire an existing session whose status is `stopped`, `terminated`, or
otherwise interrupted (server restart, conversation reset). Most of the time
the agent will create its own sessions — this is mainly for picking up a
previously-stopped run on user request.

### cancel_monte_carlo(session_id)

Cooperative cancel — finishes the in-flight scenario then stops.

### terminate_monte_carlo(session_id)

Hard stop — marks the session `terminated` and force-kills the worker.
Prefer `cancel_monte_carlo` unless the worker is stuck.

### purge_monte_carlo_sessions(days_old?)

Delete old sessions. If `days_old` is omitted, deletes **all** sessions.

## Standard workflow

```python
# 1. Stage the simulation (candles-only, 200 scenarios is the default)
draft = create_monte_carlo_draft(
    exchange="Binance Perpetual Futures",
    routes='[{"exchange":"Binance Perpetual Futures","strategy":"MyStrategy","symbol":"BTC-USDT","timeframe":"4h"}]',
    start_date="2023-01-01",
    finish_date="2024-01-01",
    hypothesis="MyStrategy is robust across resampled BTC price paths.",
)
sid = draft["session_id"]

# 2. Fire it
run_monte_carlo(sid)

# 3. Poll until done
while True:
    s = get_monte_carlo_session(sid)
    status = s["data"]["session"]["status"]
    if status in ("finished", "stopped", "terminated"):
        break
    time.sleep(5)

# 4. Inspect summary metrics
session = s["data"]["session"]
if status == "finished":
    candles = session["candles_session"]
    by_metric = {m["metric"]: m for m in candles["summary_metrics"]}
    sharpe = by_metric.get("sharpe_ratio", {})
    orig, med, best5, worst5 = (
        sharpe.get("original"), sharpe.get("median"),
        sharpe.get("best_5"), sharpe.get("worst_5"),
    )
    # Overfit verdict from the original-vs-MC comparison
    if orig > best5:
        verdict = "OVERFIT — original beat 95% of MC scenarios"
    elif orig > med:
        verdict = "borderline — above median MC but inside the plausible range"
    elif orig < med:
        verdict = "fantastic — original is conservative vs MC distribution"
    else:
        verdict = "good — original is representative of typical MC outcomes"
    update_monte_carlo_notes(
        sid,
        description=(
            f"Sharpe — original={orig:.2f} median={med:.2f} "
            f"best_5={best5:.2f} worst_5={worst5:.2f}. {verdict}."
        ),
    )
elif status in ("stopped", "terminated"):
    logs = get_monte_carlo_logs(sid)
    # surface logs["logs"] to the user
```

## Constraints / common errors

- **At least one mode must be enabled** — `run_trades=False` and
  `run_candles=False` is rejected. The default has `run_candles=True`.
- **At least one route is required.**
- **Strategy must exist on disk** — `strategies/<StrategyName>/__init__.py`
  must be present. Create it first.
- **Missing candles** — if the date window has no candles the runner errors.
  Don't pre-check; run the MC first and only `import_candles()` on failure
  (starting ~2 months before `start_date`).
- **409 conflict on run** — a session with that ID already exists. Create a
  new draft instead of reusing IDs across runs. Use `resume_monte_carlo` if
  you want to continue an existing session.
- **CPU-bound** — MC runs `cpu_cores` scenarios in parallel. The default
  (`cpu_count - 1`, capped at 4) is a sensible balance; override if needed.
