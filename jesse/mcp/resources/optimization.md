# Hyperparameter Optimization via MCP

Optimization tunes a strategy's `hyperparameters()` to maximize an objective
(Sharpe by default) on a **training** window, and reports each candidate's
**out-of-sample** performance on a separate **testing** window. The train/test
split is the whole point: it lets you tell a genuinely good parameter set apart
from one that's overfit to the training data.

It answers: "what parameter values work best for this strategy, and do they hold
up on data they weren't tuned on?"

## Preconditions (read before creating a draft)

1. **The strategy must declare a non-empty `hyperparameters()`** list — that list
   is what gets optimized. A strategy with no hyperparameters cannot be optimized
   and the run stops with an `InvalidStrategy` error. Each entry looks like:
   ```python
   def hyperparameters(self):
       return [
           {'name': 'fast_period', 'type': int, 'min': 5, 'max': 25, 'default': 10},
           {'name': 'slow_period', 'type': int, 'min': 26, 'max': 60, 'default': 30},
       ]
   ```
   Types: `int`, `float`, or `categorical` (with an `options` list). The strategy
   reads the chosen values via `self.hp['name']`.
2. **Candles must exist for BOTH windows** (training and testing), plus ~warm-up
   candles before each start. Don't pre-check — run it; on a candle shortage the
   session stops with a clear message telling you exactly what to import, then
   `import_candles()` and `rerun_optimization()`.

## Key concepts

| Concept | What it means |
|---|---|
| **Training window** | `training_start_date` → `training_finish_date`. The in-sample period the optimizer tunes on. |
| **Testing window** | `testing_start_date` → `testing_finish_date`. The out-of-sample period each candidate is re-evaluated on (not used for tuning). Conventionally `testing_start_date == training_finish_date` (contiguous), but any non-overlapping ranges are fine. |
| **objective_function** | What to maximize. One of `sharpe` (default), `calmar`, `sortino`, `omega`, `serenity`, `smart sharpe`, `smart sortino`. |
| **trials** | Trials **per hyperparameter**. Total trials = `n_hyperparameters × trials`. With 2 hyperparameters and `trials=200`, the optimizer runs 400 trials. Lower it (e.g. 20–50) for a quick exploratory run. |
| **best_candidates** | The ranked top parameter sets, each with training AND testing metrics. |

## Interpreting best_candidates (overfit detection)

Each finished session exposes `best_candidates`, ranked best-first by the
objective on the training window. The critical read is **training vs testing**:

| Pattern | Verdict |
|---|---|
| Strong on training **and** testing holds up close to training | **Trustworthy.** The parameters generalize — this is what you want. |
| Strong on training, **much weaker / negative on testing** | **Overfit.** Tuned to noise in the training window; don't deploy. |
| Mediocre on both | No edge from these parameters — the strategy/idea may not work. |
| Weak on training but strong on testing | Usually luck on the test window; treat with suspicion, prefer consistency. |

Each candidate carries:
- `rank` (`#1` is best by the training objective), `trial`, `params` (the tuned
  values), `fitness` (the objective score), `dna` (a compact encoding),
- `training_metrics` and `testing_metrics` (full metric dicts each),
- `objective_metric` — a convenient `"<train> / <test>"` summary on the chosen
  objective.

**Don't just pick rank #1.** Rank is by *training* fitness; the right choice is
the candidate whose **testing** metrics hold up best relative to its training
metrics (smallest train→test degradation), among the strong performers.

## Tool reference

### create_optimization_draft()
Stages a draft you can then run.
- `exchange` (default `"Binance Perpetual Futures"`)
- `routes` — JSON string array of route objects
- `data_routes` — JSON string array (default `"[]"`)
- `training_start_date`, `training_finish_date` — `YYYY-MM-DD`
- `testing_start_date`, `testing_finish_date` — `YYYY-MM-DD`
- `optimal_total` — int, target number of best candidates to surface (default 50)
- `objective_function` — str (default `"sharpe"`; see list above)
- `trials` — int, per hyperparameter (default 200)
- `best_candidates_count` — int (default 20)
- `warm_up_candles` — int (default 210)
- `fast_mode` — bool (default True)
- `cpu_cores` — int (default `cpu_count - 1`, capped at 4)
- `title`, `description`, `strategy_summary`, `hypothesis`, `rationale` — optional
  notes metadata; auto-generated if omitted

Returns: `{ "status": "success", "session_id": "<uuid>", ... }`

### update_optimization_draft(session_id, state)
Replace the whole `state` on an existing draft (read-modify-write).

### update_optimization_notes(session_id, title?, description?, strategy_codes?)
Update notes — typically to record the chosen parameters and conclusion.

### get_optimization_session(session_id)
Fetch full details — the primary polling tool.
```json
{
  "data": { "session": {
    "id": "<uuid>",
    "status": "running",
    "completed_trials": 120,
    "total_trials": 400,
    "best_candidates": [
      { "rank": "#1", "trial": "Trial 18",
        "params": {"fast_period": 12, "slow_period": 35},
        "fitness": 0.48, "dna": "...",
        "training_metrics": {"sharpe_ratio": 2.13, "total": 38, ...},
        "testing_metrics":  {"sharpe_ratio": 1.72, "total": 17, ...},
        "objective_metric": "2.13 / 1.72" }
    ],
    "objective_curve": [...],
    "exception": null, "traceback": null
  } },
  "error": null, "message": "Optimization session retrieved successfully"
}
```

### get_optimization_sessions(limit?, offset?, title_search?, status_filter?, date_filter?)
List sessions (most recent first). `status_filter`: `draft`, `running`, `paused`,
`finished`, `stopped`, `terminated`.

### get_optimization_logs(session_id)
Fetch the log file content. Useful when `status == "stopped"` to find the
underlying error, or to watch trial-by-trial progress on a long run.

### run_optimization(session_id)
Fire-and-poll. Returns `{ "status": "started", ... }` when the server accepts.
Then keep checking `get_optimization_session` until a terminal status. See
"Checking for results" below.

### rerun_optimization(session_id)
Reset (clears prior trials/best_candidates) and restart an existing session. Use
this to run a finished/stopped session again — e.g. after importing missing
candles or editing the strategy. Cancel a running session first.

### cancel_optimization(session_id)
Cooperative cancel — stops at the next trial checkpoint; completed trials are kept.

### terminate_optimization(session_id)
Hard stop — marks the session `terminated` and force-kills the worker. Prefer
`cancel_optimization` unless the worker is stuck.

### purge_optimization_sessions(days_old?)
Delete old sessions. If `days_old` is omitted, deletes **all** sessions.

## Checking for results

Optimization is the **slowest** of the modes — it runs `n_hyperparameters ×
trials` backtests, each on both the training and testing windows. Keep checking
until a terminal status (`finished`, `stopped`, `terminated`); never ask the user
to drive the loop. Watch `completed_trials / total_trials` for progress and ETA.

Adaptive check schedule (when `status == "running"`):

| Elapsed since fire | Check every |
|---|---|
| 0 – 1 min | 5 s |
| 1 – 5 min | 20 s |
| 5 – 30 min | 60 s |
| 30 – 120 min | 2 – 3 min |
| > 2 h | 5 min |

If `completed_trials > 0`, estimate ETA as
`elapsed × (total_trials / completed_trials)` and set the next check to roughly
`min(remaining_eta / 5, max_interval)`.

Status semantics:
- `running` / `paused` → keep checking
- `finished` → read `best_candidates`; report the train-vs-test verdict
- `stopped` → run failed; read `exception` (e.g. missing candles, or the strategy
  has no hyperparameters) and `get_optimization_logs(sid)`, then report it
- `terminated` → user-initiated stop; report the partial state, don't retry
  without the user's say-so

User-facing language: say **"checking for results"** in chat, not "polling".

## Standard workflow

```python
# 1. Stage the optimization (train then test, contiguous windows)
draft = create_optimization_draft(
    exchange="Binance Perpetual Futures",
    routes='[{"exchange":"Binance Perpetual Futures","strategy":"MyStrategy","symbol":"BTC-USDT","timeframe":"4h"}]',
    training_start_date="2023-01-01", training_finish_date="2024-06-01",
    testing_start_date="2024-06-01",  testing_finish_date="2024-12-01",
    objective_function="sharpe", trials=100,
    hypothesis="MyStrategy's EMA periods generalize out-of-sample.",
)
sid = draft["session_id"]

# 2. Fire it
run_optimization(sid)

# 3. Keep checking until terminal (optimization is slow — widen the interval)
while True:
    s = get_optimization_session(sid)
    status = s["data"]["session"]["status"]
    if status in ("finished", "stopped", "terminated"):
        break
    time.sleep(20)

# 4. Pick the candidate that generalizes best (smallest train->test drop)
session = s["data"]["session"]
if status == "finished":
    cands = session["best_candidates"]
    # report rank #1 plus train-vs-test for the top few; flag overfit candidates
elif status == "stopped":
    # read session["exception"] / get_optimization_logs(sid); if missing candles,
    # import_candles() for both windows (~2 months before each start) then rerun_optimization(sid)
    ...
```

## Constraints / common errors

- **Strategy needs `hyperparameters()`** — empty list → `InvalidStrategy`, nothing
  to optimize.
- **Candles for BOTH windows** — a shortage stops the session with a message
  naming both windows; `import_candles()` then `rerun_optimization()`.
- **`trials` is per-hyperparameter** — total = `n_hyperparameters × trials`. Don't
  set it huge on a multi-hyperparameter strategy unless you want a very long run.
- **At least one route is required.**
- **409 on the main endpoint** — the draft row already exists, which is why
  `run_optimization` fires via the resume endpoint; you don't normally hit this.
- **CPU- and time-bound** — far heavier than a single backtest. Use a smaller
  `trials` and short windows for a quick exploratory pass, then scale up.
