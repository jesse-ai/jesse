## Tool Reference

### create_backtest_draft()

Creates a new backtest session draft with specified parameters.

Parameters:
- `exchange` (optional): Exchange name (default: "Binance Perpetual Futures")
- `routes`: JSON string array of route configurations
- `data_routes` (optional): JSON string array of data route configurations
- `start_date` (optional): Backtest start date (default: "2025-01-01")
- `finish_date` (optional): Backtest end date (default: "2025-03-01")
- Additional options: debug_mode, export_csv, export_json, export_chart, fast_mode, benchmark

Default Configuration:
```json
{
    "exchange": "Binance Perpetual Futures",
    "routes": "[{"exchange":"Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT",    "timeframe": "4h"}]",
    "data_routes": "[]",
    "start_date": "2025-01-01",
    "finish_date": "2025-03-01",
    "debug_mode": false,
    "export_csv": false,
    "export_json": false,
    "export_chart": true,
    "export_tradingview": false,
    "fast_mode": false,
    "benchmark": true
}
```

Returns: Session ID (UUID format) and configuration object

### update_backtest_draft()

Updates an existing backtest draft configuration.

Parameters:
- `backtest_id`: UUID of the backtest session to update (required)
- `state`: JSON string with complete state object

State Parameter Format:
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

Automatically loads the current backtest configuration from the database
and merges it with the session form data.

Parameters:
- `session_id`: UUID of the backtest session to run
- `timeout_seconds` (optional): Maximum wait time (default: 24 hours)

**Workflow**:
```python
# Simply pass session_id - config is auto-loaded
result = run_backtest(session_id)
```

Process:
1. Loads current backtest configuration from database
2. Parses configuration and merges with session form data
3. Validates against BacktestRequestJson model
4. Starts backtest execution
5. Monitors progress via WebSocket events

Returns: Success message with metrics or error details

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

# Check results
session_details = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
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

**Cause**: Attempting to access multi-timeframe data within a single strategy.

**Solution**: Jesse strategies run on one timeframe. Use separate backtests for multi-timeframe analysis.

### Configuration Loading Error

**Error**: `Failed to load backtest config: [error message]`

**Cause**: Database connectivity issue or corrupted configuration.

**Solution**: Check Jesse database status and configuration validity.

**Note**: For comprehensive strategy development troubleshooting, see `jesse://strategy-development-issues`

### Other Common Errors

- Missing Data: Import candle data before backtesting
- Configuration Errors: Check JSON structure and parameter formats
- Timeout Issues: Adjust timeout_seconds parameter (default: 86400 = 24 hours)
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

# Compare results across sessions
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

PROBLEM: Attempting to access higher timeframe data within strategy logic
```
# WRONG - This doesn't work as expected
candles_4h = self.get_candles('4h')
candles_1h = self.get_candles('1h')
```

SOLUTION: Jesse strategies run on a single timeframe. For multi-timeframe strategies:
- Create separate backtests for each timeframe
- Use the primary timeframe for execution
- Access indicators from the strategy's assigned timeframe only

CORRECT APPROACH: Run separate backtests for different timeframes
```
# Backtest 1: 4h timeframe strategy
{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}

# Backtest 2: 1h timeframe strategy
{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}
```

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
→ Strategies work on single timeframe; use separate backtests for multi-timeframe

"'Strategy' object has no attribute 'capital'"
→ Use self.balance instead of self.capital

"InvalidRoutes: each exchange-symbol pair can be traded only once"
→ Run separate backtests for different timeframes of same symbol
