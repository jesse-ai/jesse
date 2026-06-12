### Jesse Strategy Template Reference

Strategies inherit from `Strategy` and define entry and exit logic. This is the central reference for the strategy class: lifecycle, order placement, the `self.*` API, position sizing, exits, multi-timeframe, futures-vs-spot, and optimization prep.

> Complete, runnable example strategies (trend-following, mean-reversion, pairs-trading, etc.) live in **jesse://strategy_examples**. Keep snippets here short; consult that resource for full classes.
> Indicator discovery and per-indicator signatures: **jesse://indicator**. Utility-function signatures: **jesse://utilities**. Sizing/risk reference: **jesse://position_risk**.

## Creating Strategies

Use the `create_strategy` tool with both name and complete content:

```python
strategy_code = '''
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils

class MyStrategy(Strategy):
    def should_long(self) -> bool:
        # Entry condition for long positions
        return False

    def should_short(self) -> bool:
        # Entry condition for short positions
        return False

    def go_long(self):
        # Place long entry order
        qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
        self.buy = qty, self.price

    def go_short(self):
        # Place short entry order
        qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
        self.sell = qty, self.price

    def should_cancel_entry(self) -> bool:
        # Cancel pending entry orders
        return False

    def update_position(self):
        # Manage open positions and implement exit logic
        pass
'''

result = create_strategy("MyStrategy", strategy_code)
```

## Required Methods

- **should_long() -> bool**: Return True to enter long positions. (`@abstractmethod` — must override.)
- **should_short() -> bool**: Return True to enter short positions. Default returns `False`.
- **go_long()**: Place buy orders for long entries (set `self.buy`). (`@abstractmethod` — must override.)
- **go_short()**: Place sell orders for short entries (set `self.sell`). Default `pass`.
- **should_cancel_entry() -> bool**: Return True to cancel still-unfilled entry orders on the next candle. Default `True`.
- **update_position()**: Manage open positions and implement exit logic. Default `pass`. Called each candle while a position is open.

## Optional Methods

- **before()**: Runs before the strategy logic each candle.
- **after()**: Runs after the strategy logic each candle (typical place for chart annotations — see below).

## Strategy Execution Model (every candle)

Strategy logic runs once per candle, after the candle has **closed**, in this sequence:

```
before()

if has_open_position:
    update_position()          # update stop_loss/take_profit, or liquidate
else:
    if has_active_entry_orders:
        if should_cancel_entry():
            # framework cancels the remaining unfilled entry orders
    else:
        if should_long():
            go_long()          # set self.buy
        if should_short():
            go_short()         # set self.sell
        # if filters() are defined, they must all pass before entry orders are submitted
        # the framework then submits the entry orders you defined

after()
```

Important notes about the flow:
- `should_long()`, `should_short()`, and `should_cancel_entry()` are **not** called while a position is open — only `update_position()` runs in that case.
- Order cancellation on position closure is handled automatically by the framework.
- If you define `filters()` (see below), all of them must pass before any entry orders are submitted.
- The price/close fed to your logic is the **closing price of the current (already closed) candle** — lookahead bias is handled internally (see Common mistakes).

## Lifecycle & Event Hooks

Override any of these to run custom logic at specific points. They all default to `pass` (no-op) unless noted.

| Hook | When it fires |
|---|---|
| `before()` | Start of every candle, before entry/exit logic. |
| `after()` | End of every candle, after entry/exit logic. |
| `update_position()` | Every candle **while a position is open**. Reassign `self.stop_loss` / `self.take_profit` or call `self.liquidate()` here. |
| `should_cancel_entry() -> bool` | Each candle while entry orders are pending and no position is open. Return `True` (default) to cancel unfilled entries. |
| `on_open_position(order)` | After a position is opened. |
| `on_close_position(order, closed_trade)` | When a position is **fully** closed. **Takes TWO positional args:** the closing `order` and the just-closed `ClosedTrade`. |
| `on_increased_position(order)` | When position size increases (additional fill in the same direction). |
| `on_reduced_position(order)` | When position size is partially reduced. |

For multi-route / multi-strategy setups, the framework also calls "route" variants on **other** strategies when this one acts: `on_route_open_position`, `on_route_close_position`, `on_route_increased_position`, `on_route_reduced_position`, `on_route_canceled`. Use these for cross-route coordination (and `self.shared_vars` to pass data between routes).

> `on_close_position` **must** be defined with two parameters: `def on_close_position(self, order, closed_trade) -> None`. Defining it with only `(self, order)` raises a `TypeError` at runtime, because the framework calls it as `self.on_close_position(order, closed_trade)`.

Example — set stop/take in `on_open_position` (required for spot, recommended for futures), checking position type first:

```python
def on_open_position(self, order) -> None:
    if self.is_long:
        self.stop_loss = self.position.qty, self.price - ta.atr(self.candles) * 2
        self.take_profit = self.position.qty, self.price + ta.atr(self.candles) * 4
    elif self.is_short:
        self.stop_loss = self.position.qty, self.price + ta.atr(self.candles) * 2
        self.take_profit = self.position.qty, self.price - ta.atr(self.candles) * 4
```

## Order Placement & the Smart-Order Mechanism

Set orders by assigning a `(qty, price)` tuple (or a list of tuples for multiple price levels):

- `self.buy = qty, price` — long entry (in `go_long()`).
- `self.sell = qty, price` — short entry (in `go_short()`).
- `self.stop_loss = qty, price` — protective stop (futures: in `go_long`/`go_short` or `on_open_position`; spot: in `on_open_position`/`update_position`).
- `self.take_profit = qty, price` — profit target (same placement rules as stop_loss).

Jesse uses a **smart order mechanism**: you never specify market/limit/stop explicitly. The order type is inferred from the order price vs the current price:

```python
# market order  (price == current price)
self.buy = qty, self.price

# limit order   (buy below current price)
self.buy = qty, self.price - 10

# stop order    (buy above current price)
self.buy = qty, self.price + 10
```

For **sell** orders the relationship is inverted: a sell **above** the current price is a limit order, and a sell **below** the current price is a stop order. The same near/limit/stop routing applies to exit orders (`stop_loss` / `take_profit`).

Multiple price levels (scaling in/out) — pass a list of tuples:

```python
def go_long(self):
    # average_entry_price will be 110
    self.buy = [
        (1, 100),
        (1, 120),
    ]
```

## Position Sizing

Always derive size from available margin, price, and fee rate — **never** hardcode a fixed quantity. Two idiomatic helpers (full signatures in jesse://utilities):

```python
from jesse import utils

# size_to_qty(position_size, entry_price, precision=3, fee_rate=0) -> float
# Allocate a fraction of available margin to the position:
qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)

# risk_to_qty(capital, risk_per_capital, entry_price, stop_loss_price, precision=8, fee_rate=0) -> float
# Size so that a stop-out loses a fixed % of capital (here 3%):
entry = self.price - ta.atr(self.candles)
stop  = entry - ta.atr(self.candles) * 2.5
qty   = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate)
self.buy = qty, entry
```

Note: `risk_per_capital` is a **percentage** (e.g. `3` means 3%, not `0.03`). `size_to_qty` default precision is `3`; `risk_to_qty` default precision is `8`.

## Exit Logic

- **`self.liquidate()`** — closes the open position immediately with a market order (Jesse sets a take_profit if PnL is positive, otherwise a stop_loss, at `(position.qty, price)`).
- **`self.stop_loss = qty, price`** and **`self.take_profit = qty, price`** — protective exits.
- **Futures**: you may set `self.stop_loss` / `self.take_profit` directly in `go_long()` / `go_short()` (or, preferably, in `on_open_position()`).
- **Spot**: you may **not** set `self.stop_loss` / `self.take_profit` inside `go_long()` (it raises `InvalidStrategy`). Set them in `on_open_position()`, or implement exits manually in `update_position()` with `self.liquidate()`.

### Trailing stop (the correct pattern)

There is **no** `self.trailing_stop` attribute. Implement a trailing stop by reassigning `self.stop_loss` inside `update_position()`, ratcheting it toward price. Read the current stop with **`self.average_stop_loss`** (not `self.stop_loss[1]` — see Common mistakes):

```python
def update_position(self) -> None:
    if self.is_long:
        # ratchet the stop up: never lower than its current level
        self.stop_loss = self.position.qty, max(self.average_stop_loss, self.ema)
    elif self.is_short:
        # ratchet the stop down
        self.stop_loss = self.position.qty, min(self.average_stop_loss, self.ema)
```

The framework detects the reassignment, cancels the old stop order, and submits the new one automatically.

## `self.*` Properties & Methods Reference

Access these as `self.<name>`. Prices come from the **current (closed) candle**.

### Prices & candles

| Member | Type | Meaning |
|---|---|---|
| `price` | float | Current/closing price (alias of `close`; cached for the candle cycle). |
| `open` | float | Current candle's open (`current_candle[1]`). |
| `close` | float | Current candle's close (`current_candle[2]`). |
| `high` | float | Current candle's high (`current_candle[3]`). |
| `low` | float | Current candle's low (`current_candle[4]`). |
| `volume` | float | Current candle's volume (`current_candle[5]`). |
| `current_candle` | np.ndarray | `[timestamp, open, close, high, low, volume]` — note the order: **close is index 2**, then high, then low (not standard OHLCV ordering). |
| `candles` | np.ndarray | All candles for the current route; feed these to indicators. |
| `get_candles(exchange, symbol, timeframe)` | np.ndarray | Candles for any exchange/symbol/timeframe (multi-timeframe — see below). |

### Account & sizing

| Member | Type | Meaning |
|---|---|---|
| `available_margin` | float | Free margin = balance − margin used by open positions/orders. **Most recommended for sizing.** |
| `leveraged_available_margin` | float | `leverage * available_margin`. |
| `balance` | float | Wallet balance (USDT on futures). Updates after a position closes. |
| `portfolio_value` | float | Total portfolio value (open + closed); updates continuously. |
| `daily_balances` | list | Daily portfolio values (used for metrics like Sharpe). |
| `fee_rate` | float | Exchange fee rate, e.g. `0.001` for 0.1%. Pass to sizing helpers. |
| `leverage` | int | Configured leverage (`1` for spot). |
| `min_qty` | float | Minimum tradeable quantity. **Live/paper only** — raises in backtest. |

### Position state

| Member | Type | Meaning |
|---|---|---|
| `position` | Position | The position object (see shape below). |
| `is_open` / `is_close` | bool | Whether a position is open / closed. |
| `is_long` / `is_short` | bool | Direction of the open position. |
| `average_entry_price` | float \| None | Qty-weighted average of entry orders; available after `go_long()`/`go_short()` set `self.buy`/`self.sell`. |
| `average_stop_loss` | float | Qty-weighted average of stop-loss points. Use this to read the current stop. Raises `InvalidStrategy` if no stop is set. |
| `average_take_profit` | float | Qty-weighted average of take-profit points. Raises `InvalidStrategy` if no TP is set. |
| `increased_count` | int | Times the position size increased. |
| `reduced_count` | int | Times the position size was reduced (for multi-level exits). |
| `all_positions` | Dict[str, Position] | All positions keyed by symbol. |

The `Position` object exposes: `entry_price`, `qty`, `opened_at`, `value`, `type` (`'long'`/`'short'`/`'close'`), `pnl`, `pnl_percentage`, `is_open`.

### Orders, trades, metrics

| Member | Type | Meaning |
|---|---|---|
| `entry_orders` | List[Order] | Submitted entry orders. |
| `exit_orders` | List[Order] | Submitted exit orders. |
| `orders` | List[Order] | All orders submitted by this strategy. |
| `trades` | List[ClosedTrade] | Closed trades for this strategy. |
| `metrics` | dict | Performance metrics dictionary. |
| `routes` | List[Route] | All configured routes. |

### Environment & context

| Member | Type | Meaning |
|---|---|---|
| `symbol` / `timeframe` / `exchange` | str | The route's symbol / timeframe / exchange. |
| `index` | int | Execution counter (starts at 0, +1 each candle). Useful for periodic actions, e.g. `if self.index % 1440 == 0:`. |
| `exchange_type` | str | `'spot'` or `'futures'`. |
| `is_spot_trading` / `is_futures_trading` | bool | Market type checks. |
| `is_backtesting` / `is_livetrading` / `is_papertrading` | bool | Run-mode checks. |
| `is_live` | bool | True if live **or** paper trading. |
| `hp` | dict | Hyperparameter values keyed by name (see Optimization). |
| `vars` | dict | Per-strategy scratch dict. |
| `shared_vars` | dict | Dict shared across all routes (cross-route communication). |

### Methods

| Method | Purpose |
|---|---|
| `liquidate()` | Close the open position with a market order. |
| `get_candles(exchange, symbol, timeframe)` | Fetch candles for another timeframe/symbol. |
| `log(msg, log_type='info', send_notification=False, webhook=None)` | Log / debug message (see below). |
| `watch_list()` | Return a list of `(label, value)` tuples surfaced in live/paper monitoring. |
| `hyperparameters()` | Return the list of optimizable parameters (see Optimization). |
| `dna()` | Return a DNA string to apply optimized hyperparameters. |
| `filters()` | Return a list of filter **methods** (not called) that must all pass before entry. *Optional — prefer plain `if` conditions in `should_long`/`should_short`; only define when asked.* |
| `add_line_to_candle_chart(...)` etc. | Chart annotations (see below). |

### Debug logging with `self.log()`

`self.log()` is useful for tracing strategy behavior during a backtest:

```python
def update_position(self):
    self.log(f'Current PnL %: {self.position.pnl_percentage}')
    if self.position.pnl_percentage > 2:
        self.log('Liquidating position')
        self.liquidate()
```

### `watch_list()`

Surface key values for live/paper session monitoring by returning a list of `(label, value)` tuples:

```python
def watch_list(self):
    return [
        ('Short EMA', self.short_ema),
        ('Long EMA', self.long_ema),
        ('Trend', 1 if self.short_ema > self.long_ema else -1),
    ]
```

## Indicator Usage

```python
import jesse.indicators as ta

# Current value on the trading route's candles:
current_sma = ta.sma(self.candles, 8)
# returns a single float on the price scale (e.g. ~29543.21), NOT the period

# Sequential values (a numpy array of the indicator over all candles):
sma_series = ta.sma(self.candles, 8, sequential=True)
# -> [1.2345, 1.2346, ...]

# On candles from another exchange/symbol/timeframe:
ta.sma(self.get_candles('Binance', 'BTC-USDT', '4h'), 8)
```

Indicators that return multiple lines come back as **named tuples** — both index and attribute access work:

```python
# Tuple-style unpacking:
upperband, middleband, lowerband = ta.bollinger_bands(self.candles, 20)
# Index access:
bb = ta.bollinger_bands(self.candles, 20)
bb[0]            # upperband
# Attribute access:
bb.upperband
```

Use `crossed(series1, series2, direction=...)` (from `jesse.utils`) for crossover signals. See jesse://indicator for the full discovery workflow and per-indicator signatures.

## Multi-Timeframe

Higher-timeframe candle arrays like `candles_6h` are **not auto-provided**. Build them yourself with `self.get_candles(...)`, typically as a `@property`:

```python
@property
def candles_6h(self):
    return self.get_candles(self.exchange, self.symbol, '6h')

@property
def big_trend(self):
    k, d = ta.srsi(self.get_candles(self.exchange, self.symbol, '1D'))
    return 1 if k > d else -1 if k < d else 0
```

Lookahead bias is handled internally even across timeframes: the closing price of a higher-timeframe candle is never from the future, so you do not need to manually shift to a previous value.

## Charting Helpers

These are real `Strategy` methods for annotating the interactive backtest charts. Call them in `before()` or (typically) `after()` so they update each candle:

```python
def after(self) -> None:
    # line on the main candlestick chart (price scale)
    self.add_line_to_candle_chart('EMA20', ta.ema(self.candles, 20))
    # horizontal lines on the main chart (support/resistance)
    self.add_horizontal_line_to_candle_chart('Resistance', 50000, 'red')
    # a separate sub-chart (different scale) + a level on it
    self.add_extra_line_chart('RSI', 'RSI14', ta.rsi(self.candles, 14))
    self.add_horizontal_line_to_extra_chart('RSI', 'Overbought', 70, 'red')
```

Signatures:
- `add_line_to_candle_chart(title, value, color=None)`
- `add_horizontal_line_to_candle_chart(title, value, color=None, line_width=1.5, line_style='solid')`
- `add_extra_line_chart(chart_name, title, value, color=None)`
- `add_horizontal_line_to_extra_chart(chart_name, title, value, color=None, line_width=1.5, line_style='solid')`

## Futures vs Spot

| | Spot | Futures |
|---|---|---|
| Shorting | Not supported — `should_short()` must return `False` | Long **and** short |
| Stop-loss / take-profit | Set in `on_open_position()` (cannot set in `go_long()`) | May set in `go_long`/`go_short`, but preferably `on_open_position()` |
| Leverage | Always `1` | Configurable (`futures_leverage`) |
| Balance accounting | Changes on order submission | Changes on position close or fee charges |
| Available margin | Equals balance | Varies with open positions |

## Preparing for Optimization

Optimization tunes your strategy's **hyperparameters** with a genetic algorithm. You can optimize indicator periods, thresholds, and even a categorical choice between approaches.

### 1. Define `hyperparameters()`

Return a list of dicts. Keys: `name`, `type` (`int`, `float`, or `'categorical'`), `min`/`max` (for `int`/`float`), optional `step`, `options` (for `'categorical'`), and `default`:

```python
def hyperparameters(self) -> list:
    return [
        {'name': 'sma_period', 'type': int, 'min': 10, 'max': 200, 'default': 50},
        {'name': 'stop_loss', 'type': float, 'min': 1, 'max': 5, 'step': 0.1, 'default': 2.5},
        {'name': 'trend_method', 'type': 'categorical', 'options': ['supertrend', 'ema'], 'default': 'supertrend'},
    ]
```

Access values via `self.hp['name']`. For a boolean, use `int` with `min: 0, max: 1`.

```python
@property
def sma(self):
    return ta.sma(self.candles, self.hp['sma_period'])
```

Each parameter's `default` is used when not optimizing, so a strategy with `hyperparameters()` runs normally in a backtest.

### 2. Apply the best result via `dna()`

After optimization, pick a strong DNA string from the results and return it from `dna()` — the strategy then runs with those optimized values:

```python
def dna(self):
    return 't4'   # replace with your DNA string
```

### Operational guidance

- **Routes**: optimize uses exactly **ONE trading route** (you may add multiple extra/data routes).
- **Period**: prefer longer periods to avoid overfitting; avoid very short windows (e.g. 3 days).
- **Profitability**: the strategy should already be profitable — optimization improves a working strategy, it does not fix a losing one.
- **Optimal trades**: set the target number based on your timeframe; choose higher rather than lower (e.g. for a 6h timeframe doing 30–60 trades/year, set 60+).
- **When to stop**: no need to wait for 100% — stop once you have a few good DNAs and validate them on a separate out-of-sample period.
- **Before optimizing**: run the strategy through a backtest one more time to confirm there are no errors.

(Full optimization/MC workflow tools: see jesse://monte_carlo and the configuration's `optimization` section in jesse://configuration.)

## Common Mistakes / To Avoid

- **Reading the current stop**: use `self.average_stop_loss`, **not** `self.stop_loss[1]`. After formatting, `self.stop_loss` is a 2D numpy array `[[qty, price], ...]`, so `self.stop_loss[1]` is the *second order row* (often an `IndexError`), not the price.
  ```python
  # wrong:
  self.stop_loss = self.position.qty, max(self.stop_loss[1], self.kama)
  # correct:
  self.stop_loss = self.position.qty, max(self.average_stop_loss, self.kama)
  ```
- **No `self.trailing_stop`**: it does not exist. Implement trailing stops by reassigning `self.stop_loss` in `update_position()` (see Trailing stop above).
- **`self.position.qty` is 0 inside `go_long()`/`go_short()`** — the position is not open yet. It is meaningful only from `on_open_position()` onward. (Same for `position.entry_price`, which is `None` pre-open.)
- **Don't hardcode quantities** — derive size from `self.available_margin` / `self.price` / `self.fee_rate` via `size_to_qty` or `risk_to_qty`.
- **Lookahead bias is handled internally** — do not manually shift to a previous candle's indicator value. `self.price` is the current closed candle's close and is stable (cached) within a single candle cycle.
- **Use the default close source** — unless the user asks otherwise, don't pass an indicator's `source_type`; close is already the default.
- **Don't set indicator periods unless asked** — use each indicator's default period unless the user requests a specific one.
- **Don't write filters unless asked** — put conditions directly inside `should_long()`/`should_short()` rather than defining `filters()`.
- **No dead variables** — don't compute a `stop_loss`/value you never use. If you only set the stop later in `on_open_position()` and don't use it for sizing, don't define it in `go_long()`.
- **Check position type in `on_open_position()`** — branch on `self.is_long` / `self.is_short` before setting `stop_loss`/`take_profit`.
- **`on_close_position` takes two args** — `def on_close_position(self, order, closed_trade) -> None`.

## Utility Functions (used in strategies)

Imported via `from jesse import utils`. Full details in jesse://utilities; the ones most used in strategies:

| Function | Signature |
|---|---|
| `size_to_qty` | `size_to_qty(position_size, entry_price, precision=3, fee_rate=0) -> float` — position size → quantity. |
| `risk_to_qty` | `risk_to_qty(capital, risk_per_capital, entry_price, stop_loss_price, precision=8, fee_rate=0) -> float` — size from a risk %. |
| `qty_to_size` | `qty_to_size(qty, price) -> float` — quantity → position size. |
| `estimate_risk` | `estimate_risk(entry_price, stop_price) -> float` — `abs(entry - stop)`. |
| `limit_stop_loss` | `limit_stop_loss(entry_price, stop_price, trade_type, max_allowed_risk_percentage) -> float` — clamp a stop to a max risk %. `trade_type` is `'long'`/`'short'`. |
| `risk_to_size` | `risk_to_size(capital_size, risk_percentage, risk_per_qty, entry_price) -> float` — helper used by `risk_to_qty`. |
| `kelly_criterion` | `kelly_criterion(win_rate, ratio_avg_win_loss) -> float` — optimal fraction. |
| `crossed` | `crossed(series1, series2, direction=None, sequential=False) -> bool` — crossover detection. |
| `numpy_candles_to_dataframe` | `numpy_candles_to_dataframe(candles, name_date='date', name_open='open', name_high='high', name_low='low', name_close='close', name_volume='volume') -> pd.DataFrame`. |
| `anchor_timeframe` | `anchor_timeframe(timeframe) -> str` — map a timeframe to its larger anchor. |

### Pairs / statistical-arbitrage helpers

For pairs trading and cointegration-based strategies:

| Function | Signature |
|---|---|
| `prices_to_returns` | `prices_to_returns(price_series: np.ndarray) -> np.ndarray` — price series → % returns. |
| `z_score` | `z_score(series: np.ndarray) -> np.ndarray` — standardize a series (distance from mean in std devs). |
| `are_cointegrated` | `are_cointegrated(price_returns_1, price_returns_2, cutoff=0.05) -> bool` — cointegration test on two return series. |
| `calculate_alpha_beta` | `calculate_alpha_beta(returns1: np.ndarray, returns2: np.ndarray) -> tuple` — OLS `(alpha, beta)` of `returns1` on `returns2`. |
| `combinations_without_repeat` | `combinations_without_repeat(a: np.ndarray, n: int = 2) -> np.ndarray` — all permutations (useful in optimization). |

A full multi-route pairs-trading example using these (with `self.shared_vars` for cross-route data) lives in jesse://strategy_examples.
