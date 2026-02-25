### Jesse Strategy Template Reference

Strategies inherit from Strategy and define entry and exit logic.

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

- **should_long() -> bool**: Return True to enter long positions
- **should_short() -> bool**: Return True to enter short positions
- **go_long()**: Place buy orders for long entries
- **go_short()**: Place sell orders for short entries
- **should_cancel_entry() -> bool**: Return True to cancel pending entries
- **update_position()**: Manage open positions, implement exit logic

## Optional Methods

- **before()**: Executed before candle processing
- **after()**: Executed after candle processing

## Jesse Strategy Execution Model

Strategy logic runs once per candle in this sequence:

```
before()

if position_open:
    update_position()
else:
    if entry_orders_exist:
        if should_cancel_entry():
            cancel_orders()
    else:
        if should_long():
            go_long()
        if should_short():
            go_short()

after()
```

## Entry Logic

- Implement conditions in `should_long()` and `should_short()`
- Use technical indicators via `ta.indicator_name()`
- Return `True` when conditions are met, `False` otherwise

## Order Placement

- Place orders in `go_long()` and `go_short()` methods
- Use `self.buy = quantity, price` for long entries
- Use `self.sell = quantity, price` for short entries
- Calculate position size with `utils.size_to_qty()`

## Exit Logic

- Implement exit conditions in `update_position()`
- Use `self.liquidate()` to close positions
- Set `self.stop_loss` and `self.take_profit` in entry methods (futures only)
- For spot trading, implement exit logic manually in `update_position()`

## Position Sizing

```python
# Risk-based sizing (recommended)
risk_amount = self.available_margin * 0.05  # 5% of available margin
qty = utils.size_to_qty(risk_amount, self.price, fee_rate=self.fee_rate)

# Fixed percentage sizing
qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
```

## Indicator Usage

```python
import jesse.indicators as ta

# Simple indicators
sma = ta.sma(self.candles, period=20)
rsi = ta.rsi(self.candles, period=14)

# Complex indicators (return namedtuples)
macd_result = ta.macd(self.candles)
upper, middle, lower = ta.bollinger_bands(self.candles)
```