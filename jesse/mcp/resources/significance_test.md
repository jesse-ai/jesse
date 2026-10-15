# Rule Significance Testing (RST) via MCP

Rule Significance Testing checks whether a strategy's entry conditions predict
the direction of the next bar after market drift is removed. It records
`should_long()` / `should_short()` without placing orders, then applies a
stationary bootstrap to the zero-centred next-bar rule-return series.

**Run it only when the user asks for it.** It is an optional diagnostic, not a
required step before writing, backtesting, or improving a strategy.

## When to use

- The user asks "is this entry signal any good?" / "validate this signal" /
  "run a significance test".
  → Wrap the signal in a minimal entry-only strategy if none exists, RST it on a
  meaningful date window, and report the p-value.
- The user has a finished strategy with mediocre results and asks whether the
  entries themselves are weak (vs. exits being weak).
- Do not run it unasked, and do not stop strategy work because of its result.

## Interpreting results

| `p_value` | Meaning |
|-----------|---------|
| `< 0.05`  | Statistically significant evidence of next-bar entry edge. |
| `0.05 – 0.10` | Borderline. Surface the number to the user, flag as inconclusive, consider widening the window or raising `n_simulations`. |
| `> 0.10`  | No reliable next-bar entry edge. This is not a verdict on the full strategy or on multi-bar holding behavior. |

Always report `observed_mean`, `annualized_return`, `p_value`, `n_simulations`,
and `n_observations` to the user.

## Tool reference

### create_significance_test_draft()

Creates a draft session you can then run.

- `exchange` (default `"Binance Perpetual Futures"`)
- `routes` — JSON string array with **exactly one** route object
- `data_routes` — JSON string array (default `"[]"`)
- `start_date`, `finish_date` — `YYYY-MM-DD`
- `n_simulations` — int (default `2000`; recommend `2000+`)
- `random_seed` — optional int for reproducibility
- `title`, `description` — optional; auto-generated otherwise
- `strategy_summary`, `hypothesis`, `rationale` — optional, populate the
  Markdown description

Returns: `{ "status": "success", "session_id": "<uuid>", ... }`

### update_significance_test_draft(session_id, state)

Replace the whole `state` (form + results) on an existing draft. Use the same
read-modify-write pattern as `update_backtest_draft`.

### update_significance_test_notes(session_id, title?, description?, strategy_codes?)

Update notes after the test finishes — typical use is recording the conclusion.

### get_significance_test_session(session_id)

Fetch full details, including `status` and (when finished) `results`:

```json
{
  "data": {
    "session": {
      "id": "<uuid>",
      "status": "finished",
      "state": { "form": {...}, "results": {...} },
      "results": {
        "observed_mean": 0.0021,
        "annualized_return": 0.53,
        "p_value": 0.012,
        "n_simulations": 2000,
        "n_observations": 84
      }
    }
  },
  "error": null,
  "message": "Significance test session retrieved successfully"
}
```

### get_significance_test_sessions(limit?, offset?, title_search?, status_filter?, date_filter?)

List sessions (most recent first). `status_filter` values: `draft`, `running`,
`finished`, `stopped`, `terminated`. `date_filter` values: `7_days`, `30_days`,
`90_days`.

### run_significance_test(session_id)

Fire-and-poll. Returns `{ "status": "started", "session_id": ... }` immediately
when the server accepts (HTTP 202). Then poll `get_significance_test_session`
every few seconds until `status == "finished"` (or `stopped` / `terminated`).

### cancel_significance_test(session_id)

Cancel a running test.

### purge_significance_test_sessions(days_old?)

Delete old sessions. If `days_old` is omitted, deletes **all** sessions.

## Standard workflow

```python
# 1. Make sure the candidate strategy exists
write_strategy("RSIOversoldEntry", code=minimal_signal_only_code)

# 2. Stage the test
draft = create_significance_test_draft(
    exchange="Binance Perpetual Futures",
    routes='[{"exchange":"Binance Perpetual Futures","strategy":"RSIOversoldEntry","symbol":"BTC-USDT","timeframe":"4h"}]',
    start_date="2022-01-01",
    finish_date="2024-01-01",
    n_simulations=2000,
    hypothesis="Buying BTC 4h when RSI(14) < 30 produces above-random forward returns.",
)
sid = draft["session_id"]

# 3. Fire it
run_significance_test(sid)

# 4. Poll until done
while True:
    s = get_significance_test_session(sid)
    status = s["data"]["session"]["status"]
    if status in ("finished", "stopped", "terminated"):
        break
    time.sleep(3)

# 5. Inspect
session = s["data"]["session"]
if status == "finished":
    r = session["results"]
    edge = "confirmed" if r["p_value"] < 0.05 else "not confirmed"
    update_significance_test_notes(
        sid,
        description=f"p_value={r['p_value']:.3f} → edge {edge}.",
    )
```

## Constraints / common errors

- **Exactly one trading route** — the controller and runner both reject lists
  with 0 or >1 routes.
- **Strategy must exist on disk** — `strategies/<StrategyName>/__init__.py`
  must be present. Create it first.
- **Missing candles** — if the date window has no candles, the runner errors.
  Run `import_candles()` first (starting ~2 months before `start_date`).
- **409 conflict on run** — a non-draft session with that ID already exists.
  Create a new draft instead of reusing IDs across runs.
