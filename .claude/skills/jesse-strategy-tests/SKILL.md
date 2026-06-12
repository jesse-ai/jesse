---
name: jesse-strategy-tests
description: Use when writing or modifying tests for Jesse's backend — especially behavior tied to a strategy (entries/exits, take-profit/stop-loss, position lifecycle hooks, closed-trade metrics). Documents this repo's strategy-driven test pattern: a thin test in tests/test_parent_strategy.py that runs single_route_backtest('Name'), plus a test strategy class under jesse/strategies/<Name>/__init__.py whose lifecycle hooks contain the assertions.
---

# Writing tests for Jesse's backend

When a feature is tied to **strategy behavior**, write it the way the rest of the
suite does: a tiny test function that runs a backtest against a purpose-built test
strategy, where the **assertions live inside the strategy's lifecycle hooks** — not
in the test function.

## The pattern (canonical example)

**1. The test** — a one-liner in `tests/test_parent_strategy.py` that just runs the strategy:

```python
def test_on_close_position():
    single_route_backtest('TestOnClosePosition')
```

**2. The strategy** — `jesse/strategies/TestOnClosePosition/__init__.py`. The class name,
the directory name, and the string passed to `single_route_backtest` must all match:

```python
from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestOnClosePosition(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        if self.price == 10:
            self.buy = 1, self.price

    def on_open_position(self, order):
        self.take_profit = 1, 12  # close the position at 12

    def on_close_position(self, order, closed_trade) -> None:
        assert closed_trade.exit_price == 12
        assert closed_trade.entry_price == 10
        assert closed_trade.qty == 1
        assert closed_trade.type == "long"
        assert closed_trade.timeframe == self.timeframe
        assert closed_trade.exchange == self.exchange
        assert closed_trade.symbol == self.symbol
```

The assertions run during the backtest, inside `on_close_position`. If any fail, the
backtest raises and the test fails. The test function itself stays assertion-free.

## How the price moves (so triggers like `self.price == 10` work)

`single_route_backtest('Name')` defaults to: **futures, leverage 1, fee 0, 1m timeframe,
up-trend, 100 candles**. The up-trend candles have close prices `1, 2, 3, … , 99`
(`candles_from_close_prices(range(1, 100))`). So `self.price` walks `1 → 99`, one step
per candle. That's why:
- `should_long` / `go_long` fire when `self.price == 10` (the 10th candle),
- a `take_profit` at `12` fills two candles later as price rises through it.

Use `trend='down'` for descending prices (`100 → 11`), e.g. to exercise short trades or
stop-losses.

### `single_route_backtest` parameters

```python
single_route_backtest(
    strategy_name,            # 'TestXyz' — matches class & directory name
    is_futures_trading=True,
    leverage=1,
    leverage_mode='cross',    # or 'isolated'
    trend='up',               # 'up' -> 1..99, 'down' -> 100..11
    fee=0,                    # e.g. 0.0004 to test fees
    candles_count=100,
    timeframe='1m',
)
```

For multi-route scenarios use `two_routes_backtest(name1, name2, ...)` or
`two_data_routes_backtest(...)` from `jesse.testing_utils`.

## More patterns

### Asserting engine/exchange state at a chosen candle (`before`/`after`)

You don't have to assert on the closed trade. To check engine state — balances,
exchange internals — assert inside `before()` (or `after()`) gated on a specific
price/candle, and reach into the store for the raw objects. This spot example runs a
**down-trend** (`trend='down'` → prices `100 → 11`), opens at 100 with a TP/SL, then
verifies the balance settled correctly on a later candle:

```python
def test_proper_balance_handling_in_spot_after_order_cancellation():
    single_route_backtest(
        'TestProperBalanceHanldingInSpotAfterOrderCancellation',
        is_futures_trading=False, trend='down',
    )
```

```python
from jesse.strategies import Strategy
from jesse import utils
from jesse.store import store


class TestProperBalanceHanldingInSpotAfterOrderCancellation(Strategy):
    def before(self) -> None:
        # after the first trade has fully resolved
        if self.price == 89:
            assert self.balance == 9900
            e = store.exchanges.get_exchange(self.exchange)
            assert e.assets['USDT'] == 9900
            assert e.assets['BTC'] == 0

    def should_long(self):
        return self.price == 100

    def go_long(self):
        entry = self.price
        qty = utils.size_to_qty(1000, entry)
        self.buy = qty, entry

    def on_open_position(self, order):
        self.take_profit = self.position.qty, 110
        self.stop_loss = self.position.qty, 90
```

Notes:
- `is_futures_trading=False` selects **spot**, where the exchange tracks per-asset
  balances (`e.assets['USDT']`, `e.assets['BTC']`) rather than a single wallet.
- `store.exchanges.get_exchange(self.exchange)` is the standard way to inspect engine
  state from inside a strategy. `store.positions`, `store.orders`, `store.closed_trades`
  work the same way.
- Set exits sized to the live position with `self.position.qty`.

### Multi-route tests (`two_routes_backtest`)

To test cross-route behavior, run two strategies together — one per route — with
`two_routes_backtest(name1, name2)` (BTC-USDT and ETH-USDT, both 1m). Each strategy
asserts about its own route. These observer strategies don't trade (`should_long`
returns `False`); they exist purely to assert. Here each route checks its
`current_route_index` at specific candles via `self.index`:

```python
def test_current_route_index():
    two_routes_backtest('TestCurrentRouteIndex1', 'TestCurrentRouteIndex2')
```

```python
class TestCurrentRouteIndex1(Strategy):
    def before(self) -> None:
        if self.index == 0 or self.index == 10:
            assert self.current_route_index == 0

    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_cancel_entry(self):
        return False


class TestCurrentRouteIndex2(Strategy):
    def before(self) -> None:
        if self.index == 0 or self.index == 10:
            assert self.current_route_index == 1
    # ... same no-op should_long / go_long / should_cancel_entry
```

Notes:
- `self.index` is the 0-based candle index (vs. `self.price`, the close price). Use it
  to gate assertions when the value you're testing isn't price-derived.
- A strategy that only observes still needs `should_long`/`go_long` (and usually
  `should_cancel_entry`) defined, even as no-ops.
- Use `two_data_routes_backtest(...)` when routes need extra (non-trading) data
  timeframes.

## Lifecycle hooks where assertions go

Put assertions in whichever hook observes the thing you're testing:

| Hook | Signature | Fires when |
|------|-----------|-----------|
| `should_long` / `should_short` | `(self) -> bool` | deciding whether to enter |
| `go_long` / `go_short` | `(self)` | placing entry orders (set `self.buy`/`self.sell`) |
| `should_cancel_entry` | `(self) -> bool` | deciding to cancel a pending entry |
| `on_open_position` | `(self, order)` | position just opened (set `take_profit`/`stop_loss` here) |
| `on_increased_position` | `(self, order)` | added to an open position |
| `on_reduced_position` | `(self, order)` | partially closed (e.g. a TP filled) |
| `on_close_position` | `(self, order, closed_trade)` | position fully closed — assert final trade metrics here |
| `update_position` | `(self)` | every candle while a position is open |
| `before` / `after` | `(self)` | every candle, before/after the strategy logic |

Setting exits: `self.take_profit = qty, price` and `self.stop_loss = qty, price`
(use a list of `(qty, price)` tuples for multi-tier exits).

## Discovering the available strategy API

The hooks and properties above are the common ones, not the full set. Whenever you
need to know what a test strategy can access or do — properties (`self.balance`,
`self.position`, `self.orders`, `self.trades`, `self.metrics`, `self.average_entry_price`,
`self.current_route_index`, `self.portfolio_value`, …), helper methods
(`self.liquidate()`, `self.log()`, `self.get_candles()`), or the exact signature of a
lifecycle hook — **read the `Strategy` base class** at
`jesse/strategies/Strategy.py`. It is the source of truth; don't guess an API, confirm
it there first.

## Conventions

- **Names match**: class name == directory name == string passed to the helper.
- **Assert inside the strategy**, not in the test function, for strategy-driven tests.
- **Float comparisons**: use `round(value, 8)` when values aren't exact.
- **Fees**: pass `fee=` to the helper (or set
  `config['env']['exchanges'][exchanges.SANDBOX]['fee']` in manual setups).
- **Clean up shared state**: a test that leaves a closed trade in the global `store`
  must call `store.reset()` at the end — some test files assert an empty store at
  their start. The `single_route_backtest` helpers reset config/store on entry via
  `set_up`, so back-to-back helper-based tests are already isolated.
- **Accounting invariant**: for tests about fees/PNL, assert that per-trade
  `closed_trade.pnl` equals the real wallet balance change.

## When NOT to use the strategy-driven pattern

For **low-level engine accounting** that's awkward to express through a strategy
(exact `filled_qty`, fee-on-fill, `exit_price` VWAP under `reduce_only` caps), prefer a
**broker-level unit test** in `tests/test_broker.py`: build state with
`set_up_with_fee` / `set_up_without_fee`, then drive `broker.*` and
`order_service.execute_order(...)` directly and assert on the order, position, and
`exchange.wallet_balance`. See `test_oversized_reduce_only_order_uses_actual_filled_qty`.

## Running

```bash
# activate env and cd into jesse/
cd-jesse

# run the full strategy-test suite
pytest tests/test_parent_strategy.py -q

# run a single test by name
pytest tests/test_parent_strategy.py::test_on_close_position -q

# run all tests across every test file
pytest

# run another specific test file (e.g. broker-level tests)
pytest tests/test_broker.py -q
```

Use `-v` instead of `-q` for verbose output showing each test name as it runs.
