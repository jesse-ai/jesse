## Tool Reference

### create_backtest_draft()

Creates a new backtest session draft with specified parameters.

Parameters:
- `exchange` (optional): Exchange name (default: "Binance Perpetual Futures")
- `routes`: JSON string array of route configurations
- `data_routes` (optional): JSON string array of data route configurations
- `start_date` (optional): Backtest start date (default: "2024-01-01")
- `finish_date` (optional): Backtest end date (default: "2024-03-01")
- Additional options: debug_mode, export_csv, export_json, export_chart, fast_mode, benchmark
- `title` (optional): Note title for the MCP-created session. If omitted, MCP generates one with an `MCP Backtest:` prefix.
- `description` (optional): Full note description. If omitted, MCP generates a short markdown summary.
- `strategy_summary` (optional): One-sentence summary of the strategy being tested.
- `change_summary` (optional): What MCP changed before this backtest, if it edited a strategy.
- `rationale` (optional): Why MCP made the change or ran this test.
- Run settings (optional): `fee`, `leverage`, `leverage_mode`, `balance`, `warm_up_candles`, `config_overrides`. See Run Settings below.

Default Configuration:
```json
{
    "exchange": "Binance Perpetual Futures",
    "routes": "[{"exchange":"Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT",    "timeframe": "4h"}]",
    "data_routes": "[]",
    "start_date": "2024-01-01",
    "finish_date": "2024-03-01",
    "debug_mode": false,
    "export_csv": false,
    "export_json": false,
    "export_chart": true,
    "fast_mode": true,
    "benchmark": true
}
```

Returns: Session ID (UUID format), the draft state, and `run_config` / `config_source` / `config_warnings` (see Run Settings)

#### Run Settings

The run settings shared by all four research draft tools (backtest, optimization, Monte Carlo, significance test). Set them as arguments on create; never edit the draft state to change them.

| Argument | Meaning |
|---|---|
| `fee` | Exchange fee as a fraction per side (`0.0006` = 0.06%) |
| `leverage` | Futures leverage, a whole number >= 1. Ignored (with a warning) on spot exchanges |
| `leverage_mode` | `"cross"` or `"isolated"`; must be a mode the exchange supports |
| `balance` | Starting balance (more than 0) |
| `warm_up_candles` | Candles loaded before the start date to warm up indicators |
| `config_overrides` | JSON object for any other run-config field of the mode. Backtest: `logging` (the log flags), `warm_up_candles` and `exchange` (`fee`, `balance`, `futures_leverage`, `futures_leverage_mode`), e.g. `{"exchange": {"fee": 0.0002, "futures_leverage": 20}}`. Named arguments win over it |

- Omitted settings come from the saved backtest defaults for that exchange, else Jesse's built-in defaults (fee: the exchange's listed fee, else 0.0006; leverage 1, cross; balance 10,000; 210 warm-up candles).
- Invalid values (fee outside 0..1, fractional leverage, unsupported leverage mode, unknown `config_overrides` fields) are refused with an error and nothing is created.
- The response shows what the draft will run with:
  - `run_config`: exactly the config the draft runs with
  - `config_source`: per field, one of `explicit` (this call), `stored` (already in the draft), `tool_default` (the MCP tool's own default), `saved_default` (saved defaults for this mode and exchange), `exchange_default` (the exchange's listed fee), `hard_default` (Jesse's built-in value)
  - `config_warnings` (only when there are any): a fee or leverage that is only Jesse's built-in default, or a leverage ignored on spot. When you see one, pass the value explicitly.

MCP-created drafts automatically populate the session notes fields that the dashboard already uses:
- `title`: Short, searchable title with an `MCP Backtest:` prefix
- `description`: Markdown-formatted summary focused on strategy, change, rationale, and backtest period
- `strategy_codes`: Strategy code snapshots when the referenced strategy files are available

### update_backtest_draft()

Updates an existing backtest draft: either replaces its full state, or changes only its run settings.

Parameters:
- `backtest_id`: UUID of the backtest session to update (required)
- `state` (optional): JSON string with complete state object
- Run settings (optional): `fee`, `leverage`, `leverage_mode`, `balance`, `warm_up_candles`, `config_overrides` (same meaning as in create)

Changing only run settings (fee, leverage, ...): omit `state` and pass just the settings, e.g.
`update_backtest_draft(backtest_id, fee=0.0004, leverage=3)`. The stored draft keeps everything
else, and the response shows the new `run_config` and `config_source` (`explicit` for what this
call set, `stored` for the rest). Only drafts (status `"draft"`) can change; for a finished
session, create a new draft. Passing `state` together with run settings is an error, and so is
passing neither.

State Parameter Format (full replace, for routes, dates and other form fields):
The state parameter must contain only the inner state object:

```json
{
    "form": {
    "exchange": "Binance Perpetual Futures",
    "routes": [...],
    "start_date": "2024-01-01",
    "finish_date": "2024-03-01"
    },
    "results": {
    "showResults": false,
    "executing": false
    }
}
```

Update Process:
1. Retrieve current state with `get_backtest_session()`
2. Extract state object: `response.session.state.state`
3. Merge changes with current state
4. Call `update_backtest_draft()` with merged state

### update_backtest_notes()

Updates the existing notes metadata for a backtest session.

Parameters:
- `session_id`: UUID of the backtest session to update (required)
- `title` (optional): Short title shown in session lists
- `description` (optional): Detailed note or markdown summary
- `strategy_codes` (optional): JSON object string containing strategy code snapshots

Use this after an AI-driven iteration when the agent has learned the final hypothesis,
configuration rationale, or relevant conclusion for the session.

### get_backtest_session()

Retrieves details of a specific backtest session.

Parameters:
- `session_id`: UUID of the backtest session

Returns:
```json
{
    "data": {
        "session": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "state": {
                "form": { /* Configuration */ },
                "results": { /* Results */ }
            },
            "metrics": { /* Performance metrics */ },
            "trades": [ /* Trade history */ ]
        }
    },
    "error": null,
    "message": "Backtest session retrieved successfully"
}
```

On error:
```json
{
    "data": null,
    "error": "Error message",
    "message": "Error message"
}
```

### get_backtest_sessions()

Lists backtest sessions with pagination and filtering.

Parameters:
- `limit` (optional): Maximum sessions to return (default: 50)
- `offset` (optional): Skip N sessions for pagination (default: 0)
- `title_search` (optional): Search in session titles
- `status_filter` (optional): Filter by status ("finished", "running", "cancelled")
- `date_filter` (optional): Filter by date ("today", "this_week", "this_month")

Returns: Array of session objects sorted by most recently updated

### run_backtest()

Executes a backtest using stored session configuration.

Runs with the draft's own run config (the `run_config` shown on create/update); saved
defaults only fill fields the draft lacks.

Parameters:
- `session_id`: UUID of the backtest session to run

**Workflow**:
```python
# Simply pass session_id - config is auto-loaded
result = run_backtest(session_id)
```

Process:
1. Loads the session's form and its stored run config
2. Fills any missing run-config fields from the saved defaults
3. Validates against BacktestRequestJson model
4. Starts backtest execution
5. Monitors progress via WebSocket events

Returns: Immediate acknowledgement containing the session ID, the executed trading routes,
and dashboard URL; or error details. It does not wait: follow it with `wait_for_sessions`
(see "Waiting for runs" below).

### cancel_backtest()

Cancels a running backtest process.

Parameters:
- `session_id`: UUID of the backtest to cancel

Returns: Updated session status

### purge_backtest_sessions()

Deletes old backtest sessions from database.

Parameters:
- `days_old` (optional): Age threshold in days (null deletes all sessions)

Returns: Number of deleted sessions

### save_strategy_report()

Saves the mandatory Markdown report of an optimization/backtest task. Jesse writes it on the
machine running Jesse at `strategies/<strategy_name>/reports/<filename>` and creates the
`reports` folder if needed, so it works the same for assistants on another computer and for
Docker installs. Never write or look for reports with your own file tools.

Parameters:
- `strategy_name`: Exact name of an existing strategy
- `filename`: Bare file name ending in `.md` (letters, digits, `.`, `_`, `-`; no folders), e.g. `BTCUSDT_sharpe_optimization_report.md`
- `content`: Complete Markdown text (must not be empty)
- `overwrite` (optional, default `false`): Replace an existing report. Without it, an existing file returns `error_type: "report_exists"`; use it only to update your own report from the same task.

Returns: `path` (project-relative, e.g. `strategies/BTCSharpeIter/reports/BTCUSDT_sharpe_optimization_report.md`), `overwritten`, and `size_bytes`. The success response is the verification: give the user the `path` verbatim as a location inside the Jesse project.

## Waiting for runs

`run_backtest`, `run_optimization` / `rerun_optimization`, `run_monte_carlo` / `resume_monte_carlo`
and `run_significance_test` return as soon as the run starts. Wait for them with one tool,
`wait_for_sessions`, never with sleep-and-poll loops over `get_*_session` or `get_session_results`.
It waits on the Jesse host, reports, and never starts, stops or cancels anything.

`wait_for_sessions(session_ids, until="all", timeout_seconds=240, stall_minutes=None)`
- `session_ids`: up to 50 IDs of any research type, mixed is fine. Pass every run you started.
- `until`: `"all"` returns when every session is settled; `"any"` at the first one, so you can
  start the next run and keep a fixed number running in parallel.
- `timeout_seconds`: 0-540. If it passes first, `done` is `false`: call again with the same IDs.
- `stall_minutes`: how long a live worker may go without progress before it counts as stalled.
  Defaults: backtest 10, optimization 30 (progress is recorded per finished trial; raise it for very
  slow trials), Monte Carlo and significance test 20.

| `outcome` | Meaning | Next |
|---|---|---|
| `finished` | Completed | `get_session_results(type, id)` |
| `ended` | Stopped, cancelled or terminated; `error` says why. A dead worker (killed, out of memory, lost DB connection, machine gone) lands here within ~90 seconds | Fix the cause, run again |
| `stalled` | Worker alive, but no progress past the stall limit | Check its logs; if stuck, cancel it and run it again |
| `not_started` | Still a draft | Start it with its run tool |
| `not_found` | No session has that ID | Check the ID |
| `running` | Not settled yet; shows `progress` and `progress_age_seconds` | Keep waiting |
| `queued` | Not settled yet; waiting for a research runner (`queue` holds its target and wait time) | Keep waiting; if it waits long, check `list_runners` |

A session started by an older Jesse version has no heartbeat: it can never show as stalled,
only its end is detected. `claimed_by` names the machine running it; a run on another machine must
be cancelled through that machine's Jesse. Give the user each session's `dashboard_url`.

```python
ids = [draft_a_id, draft_b_id]
for sid in ids:
    run_backtest(sid)
w = wait_for_sessions(ids)            # repeat while w["done"] is False
for s in w["sessions"]:
    if s["outcome"] == "finished":
        get_session_results("backtest", s["session_id"])
```

### Research runners

A Jesse can have research runners: other machines sharing its database that pick up queued
research jobs. Every run tool (`run_backtest`, `run_optimization` / `rerun_optimization`,
`run_monte_carlo` / `resume_monte_carlo`, `run_significance_test`) takes `where`:

- `"auto"` (default): a free runner when this Jesse has runners turned on and one is alive, else here.
- `"local"`: always here.
- `"any"`: queue it for whichever runner is free first.
- a runner name from `list_runners`: queue it for that machine only.

A queued run returns `status: "queued"` with `target`, `job_id`, `dashboard_url` and, when no
matching runner is connected, a `warning`; it shows outcome `queued` in `wait_for_sessions` until
a runner claims it, then `running` as usual. `list_runners()` shows each runner's `alive`,
`cores_budget` / `cores_free`, `jesse_version` / `compatible`, and what it runs, plus `queued_jobs`.
A backtest or significance test uses 1 core and an optimization or Monte Carlo run its `cpu_cores`;
jobs start in queue order, and a big job waiting for cores is not overtaken on its runner. Results land in the
same database, so `get_session_results` and `run_analysis` work exactly as for a local run.
A slow queue is not a failed run: never start the same variant again because it is still queued.

## Usage Examples

### Basic Backtest Creation
```python
draft = create_backtest_draft(
    routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}]',
    start_date="2024-01-01",
    finish_date="2024-12-31"
)
# Returns: { backtest_id: "550e8400-e29b-41d4-a716-446655440000" }
```

### Configuration Override
```python
draft = create_backtest_draft(
    exchange="Binance Spot",
    routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "ETH-USDT", "timeframe": "4h"}]',
    data_routes='[{"exchange": "Binance Spot", "symbol": "ETH-USDT", "timeframe": "4h"}]',
    debug_mode=true
)
```

### Fee and Leverage
```python
draft = create_backtest_draft(
    routes='[{"exchange": "Binance Perpetual Futures", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
    fee=0.0004,
    leverage=3,
    leverage_mode="isolated"
)
# Check draft["run_config"]["exchange"] and draft.get("config_warnings")

# Later, change only the fee of the same draft
update_backtest_draft(draft["backtest_id"], fee=0.0002)
```

### Multiple Strategies
```python
routes = '''[
    {"exchange": "Binance Spot", "strategy": "Strategy1", "symbol": "BTC-USDT", "timeframe": "1h"},
    {"exchange": "Binance Spot", "strategy": "Strategy2", "symbol": "ETH-USDT", "timeframe": "4h"}
]'''

draft = create_backtest_draft(routes=routes)
```

### State Updates

Appending Routes:
```python
session_response = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
session = session_response.data.session
current_state = session.state.state
new_route = {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "DOGE-USDT", "timeframe": "1h"}
updated_routes = current_state.form.routes + [new_route]
merged_state = current_state.copy()
merged_state.form.routes = updated_routes
update_backtest_draft("550e8400-e29b-41d4-a716-446655440000", merged_state)
```

Field Updates:
```python
session_response = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
session = session_response.data.session
current_state = session.state.state
merged_state = current_state.copy()
merged_state.form.start_date = "2024-06-01"
merged_state.form.debug_mode = true
update_backtest_draft("550e8400-e29b-41d4-a716-446655440000", merged_state)
```

### Running Backtests
```python
# Config is automatically loaded from database
result = run_backtest("550e8400-e29b-41d4-a716-446655440000")

# Wait until it ends or stalls (repeat while done is False), then read results
wait_for_sessions(["550e8400-e29b-41d4-a716-446655440000"])
summary = get_session_results("backtest", "550e8400-e29b-41d4-a716-446655440000")
```

## Supported Exchanges

Jesse supports the following exchanges for backtesting and live trading:

### Spot Exchanges
- `"Binance Spot"` - Most popular, reliable data
- `"Bybit Spot"` - Alternative data source
- `"Coinbase Spot"` - Low fees (0.03%)
- `"Bitfinex Spot"` - Additional option

### Futures Exchanges
- `"Binance Perpetual Futures"` - High leverage (up to 5x)
- `"Bybit USDT Perpetual"` - Conservative leverage (up to 2x)
- `"Bybit USDC Perpetual"` - USDC settlement
- `"Gate USDT Perpetual"` - Additional futures option

## Route Configuration Schema

Route Object:
```json
{
    "exchange": "string (exchange name - see supported exchanges above)",
    "strategy": "string (strategy class name)",
    "symbol": "string (trading pair)",
    "timeframe": "string (1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1D, 3D, 1W, 1M)"
}
```

Data Route Object:
```json
{
    "exchange": "string (exchange name - see supported exchanges above)",
    "symbol": "string (trading pair)",
    "timeframe": "string (timeframe)"
}
```

## Error Handling

Common error scenarios and recovery:

### Invalid Routes Error

**Error**: `InvalidRoutes: each exchange-symbol pair can be traded only once`

**Cause**: Multiple routes with the same exchange and symbol in a single backtest.

**Problematic Configuration**:
```json
"routes": [
    {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"},
    {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}
]
```

**Solution**: Run separate backtests for different timeframes of the same symbol.

**Correct Approach**:
```python
# Backtest 1: 1h timeframe
draft1 = create_backtest_draft(
    routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}]'
)

# Backtest 2: 4h timeframe
draft2 = create_backtest_draft(
    routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]'
)
```

### Strategy Execution Errors

**Error**: `Setting self.take_profit in go_long() not supported for spot trading`

**Cause**: Attempting to set stop_loss/take_profit in go_long() for spot trading.

**Solution**: Use `update_position()` method for spot trading exits.

**Error**: `Strategy.get_candles() missing required positional argument`

**Cause**: Calling `self.get_candles()` with too few arguments — it requires all three: `exchange`, `symbol`, and `timeframe`.

**Solution**: Multi-timeframe access within a single strategy IS supported. Call `self.get_candles(self.exchange, self.symbol, '4h')` with all three arguments (Jesse handles lookahead across timeframes internally). See the Multi-Timeframe section of `jesse://strategy`.

### Configuration Loading Error

**Error**: `Failed to load backtest config: [error message]`

**Cause**: Database connectivity issue or corrupted configuration.

**Solution**: Check Jesse database status and configuration validity.

**Note**: For comprehensive strategy development troubleshooting, see `jesse://strategy-development-issues`

### Other Common Errors

- Missing Data: do NOT pre-import. Run the backtest first; if it fails with a missing-candle error, then import (starting ~2 months before `start_date`) and retry. Never call `get_existing_candles()` as a pre-flight gate.
- Configuration Errors: Check JSON structure and parameter formats
- Long runs: `wait_for_sessions` returns `done: false` at its timeout; call it again (see Waiting for runs).
- State Conflicts: Retrieve current state before updates

## Best Practices

### Strategy Development Considerations

When developing and iterating on trading strategies, session management can significantly impact your ability to analyze and compare results:

**Benefits of New Sessions:**
- Clean version control - each session preserves the exact strategy code and configuration
- Easy performance comparison across different strategy versions or parameters
- Clear audit trail for development history
- Ability to revert to previous working configurations
- Better organization when testing multiple approaches simultaneously

**When New Sessions Are Particularly Useful:**
- Testing different entry/exit logic or indicator combinations
- Significant parameter optimization (RSI levels, profit targets, risk settings)
- Comparing the same strategy across different timeframes or symbols
- Major algorithmic changes or risk management modifications

**When Session Reuse May Be Appropriate:**
- Fine-tuning parameters within an established strategy configuration
- Quick testing of minor adjustments on the same setup
- Iterative improvements to a working strategy version

**Benefits of New Sessions:**
- Clean version control and audit trail
- Each session stores complete strategy code used
- Easy comparison of performance across versions
- Clear history of development process
- Ability to revert to previous working versions

**Example Workflow:**
```python
# Iteration 1: Create new session with initial strategy
draft1 = create_backtest_draft(routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]')
run_backtest(draft1.backtest_id, config)

# Iteration 2: Create NEW session with modified strategy
draft2 = create_backtest_draft(routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]')
run_backtest(draft2.backtest_id, config)

# Wait for both, then compare results across sessions
wait_for_sessions([draft1.backtest_id, draft2.backtest_id])
session1_response = get_backtest_session(draft1.backtest_id)
session2_response = get_backtest_session(draft2.backtest_id)
session1_results = session1_response.data.session
session2_results = session2_response.data.session
```

debug_mode can assist during development
Charts and JSON exports support analysis
Resource usage monitoring helps with large backtests
Regular archiving of completed sessions improves management

### Jesse Strategy Development Issues & Solutions during backtesting

This reference covers common pitfalls and their solutions encountered during
strategy development for backtesting, based on real development experiences.

== COMMON ISSUES & SOLUTIONS ==

=== 1. Multi-Timeframe Data Access ===

PROBLEM: `self.get_candles()` raises "missing required positional argument"
```
# WRONG - get_candles needs exchange, symbol AND timeframe
candles_4h = self.get_candles('4h')
```

SOLUTION: Multi-timeframe access within ONE strategy is fully supported. Call
self.get_candles(exchange, symbol, timeframe) with all three arguments — Jesse
handles lookahead bias across timeframes internally, so a higher-timeframe
candle's close is never future data.
```
# CORRECT - read a higher timeframe inside the same strategy
candles_4h = self.get_candles(self.exchange, self.symbol, '4h')
trend_ema = ta.ema(candles_4h, 50)
```
Typically expose it as a @property (e.g. candles_4h). See the Multi-Timeframe
section of jesse://strategy for the canonical pattern.

=== 2. Balance vs Capital Confusion ===

PROBLEM: Using deprecated 'self.capital' instead of 'self.balance'
```
# WRONG
qty = utils.size_to_qty(self.capital * 0.1, self.close, fee_rate=self.fee_rate)
# ERROR: AttributeError: 'Strategy' object has no attribute 'capital'
```

SOLUTION: Use 'self.balance' for current account balance
```
# CORRECT
qty = utils.size_to_qty(self.balance * 0.1, self.close, fee_rate=self.fee_rate)
```

=== 3. Spot Trading Exit Management ===

PROBLEM: Setting stop_loss/take_profit in go_long() for spot trading
```
# WRONG - Works for futures, fails for spot
def go_long(self):
    self.buy = qty, self.close
    self.stop_loss = self.close * 0.95  # 5% stop loss
    self.take_profit = self.close * 1.10  # 10% take profit
# ERROR: Setting self.take_profit in go_long() not supported for spot trading
```

SOLUTION: Use update_position() for spot trading exits
```
# CORRECT - For spot trading
def go_long(self):
    qty = utils.size_to_qty(self.balance * 0.1, self.close, fee_rate=self.fee_rate)
    self.buy = qty, self.close

def on_open_position(self, order):
    self.entry_price = self.position.entry_price

def update_position(self):
    if self.is_long:
        # Check stop loss
        if self.close <= self.entry_price * 0.95:
            self.liquidate()
            return
        # Check take profit
        if self.close >= self.entry_price * 1.10:
            self.liquidate()
            return
```

=== 4. Futures vs Spot Trading Differences ===

PROBLEM: Using futures-style exit logic for spot trading

FUTURES TRADING (allows stop_loss/take_profit in go_long):
```
def go_long(self):
    self.buy = qty, self.price
    self.stop_loss = self.price * 0.95    # ✓ Works for futures
    self.take_profit = self.price * 1.10  # ✓ Works for futures
```

SPOT TRADING (requires update_position):
```
def go_long(self):
    self.buy = qty, self.close  # Note: use self.close, not self.price

def update_position(self):
    if self.is_long:
        if self.close <= self.entry_price * 0.95:
            self.liquidate()
        elif self.close >= self.entry_price * 1.10:
            self.liquidate()
```

=== 5. Indicator Data Requirements ===

PROBLEM: Not ensuring sufficient candle data for indicators
```
# WRONG - May fail if insufficient candles
def should_long(self):
    rsi = ta.rsi(self.candles, 14)
    return rsi < 30
```

SOLUTION: Check candle count before using indicators
```
# CORRECT
def should_long(self):
    if len(self.candles) < 14:  # RSI period
        return False
    rsi = ta.rsi(self.candles, 14)
    return rsi < 30
```

For multiple indicators, use max() to ensure all have enough data:
```
required_candles = max(self.rsi_period, self.bb_period, self.slow_ma_period)
if len(self.candles) < required_candles:
    return False
```

=== 6. Backtest Configuration Issues ===

PROBLEM: Multiple routes with same exchange-symbol pair
```
# WRONG - Causes InvalidRoutes error
"routes": [
    {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"},
    {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}
]
# ERROR: each exchange-symbol pair can be traded only once
```

SOLUTION: Run separate backtests for different timeframes
```
# CORRECT - Separate backtests
# Backtest 1: 1h timeframe
"routes": [
    {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}
]

# Backtest 2: 4h timeframe
"routes": [
    {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}
]
```

=== 7. Position Sizing Errors ===

PROBLEM: Using fixed quantities instead of dynamic sizing
```
# WRONG - Fixed quantity regardless of capital
def go_long(self):
    self.buy = 100, self.close  # Always buys 100 units
```

SOLUTION: Use dynamic position sizing based on available capital
```
# CORRECT - Size based on capital percentage
def go_long(self):
    risk_amount = self.balance * 0.05  # 5% of balance
    qty = utils.size_to_qty(risk_amount, self.close, fee_rate=self.fee_rate)
    self.buy = qty, self.close
```

=== DEBUGGING WORKFLOW ===

When encountering errors:

1. Check the error message carefully - Jesse provides specific error descriptions
2. Verify you're using the correct attributes (balance vs capital, close vs price)
3. Ensure proper method usage for spot vs futures trading
4. Confirm sufficient candle data for all indicators
5. Test with simplified logic first, then add complexity

=== TESTING BEST PRACTICES ===

- Start with simple RSI-only strategy to verify basic functionality
- Test position sizing separately from entry logic
- Use conservative position sizes (5-10% of capital) during development
- Verify exit logic works before optimizing entry conditions
- Run backtests on short time periods first to catch errors quickly

=== COMMON ERROR MESSAGES ===

"Setting self.take_profit in go_long() not supported for spot trading"
→ Use update_position() for spot trading exits

"Strategy.get_candles() missing required positional argument"
→ get_candles needs all three args: self.get_candles(self.exchange, self.symbol, '4h'). Multi-timeframe within one strategy is supported (see jesse://strategy).

"'Strategy' object has no attribute 'capital'"
→ Use self.balance instead of self.capital

"InvalidRoutes: each exchange-symbol pair can be traded only once"
→ Run separate backtests for different timeframes of same symbol
