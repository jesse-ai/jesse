### Jesse Utilities Reference

Utility functions are available through:

``` PYTHON
from jesse import utils
```
## Position Sizing

### size_to_qty(position_size, entry_price, precision=3, fee_rate=0)

Converts position size to quantity.

**Parameters:**
- `position_size`: Dollar amount to allocate
- `entry_price`: Entry price per unit
- `precision`: Quantity precision (default: 3)
- `fee_rate`: Fee rate for calculations (default: 0)

**Returns:** Quantity to trade

**Example:**
```python
# Risk 1% of $10,000 balance
position_size = 10000 * 0.01  # $100
qty = utils.size_to_qty(position_size, self.price)
```

### risk_to_qty(capital, risk_per_capital, entry_price, stop_loss_price, precision=8, fee_rate=0)

Calculates quantity based on risk parameters.

**Parameters:**
- `capital`: Available capital
- `risk_per_capital`: Risk percentage (0.01 = 1%)
- `entry_price`: Entry price
- `stop_loss_price`: Stop loss price
- `precision`: Quantity precision (default: 8)

**Returns:** Quantity that limits risk to specified percentage

### qty_to_size(qty, price)

Converts quantity to dollar position size.

**Parameters:**
- `qty`: Quantity to convert
- `price`: Price per unit

**Returns:** Position size in dollars

## Risk Management

### estimate_risk(entry_price, stop_price)

Estimates risk percentage for a trade.

**Parameters:**
- `entry_price`: Entry price
- `stop_price`: Stop loss price

**Returns:** Risk percentage (0.02 = 2%)

### limit_stop_loss(entry_price, stop_price, trade_type, max_allowed_risk_percentage)

Ensures stop loss doesn't exceed maximum allowed risk.

**Parameters:**
- `entry_price`: Entry price
- `stop_price`: Stop loss price
- `trade_type`: "long" or "short"
- `max_allowed_risk_percentage`: Maximum allowed risk (0.05 = 5%)

**Returns:** Adjusted stop price if needed

## Series Analysis

### crossed(series1, series2, direction=None, sequential=False)

Detects when one series crosses another.

**Parameters:**
- `series1`: First series (numpy array)
- `series2`: Second series (float, int, or array)
- `direction`: "above", "below", or None for any cross
- `sequential`: Check sequential candles

**Returns:** Boolean indicating if cross occurred

**Examples:**
```python
# Detect EMA cross above SMA
if utils.crossed(fast_ema, slow_sma, direction="above"):
# Fast EMA crossed above slow SMA

# Any cross (above or below)
if utils.crossed(short_ma, long_ma):
# Moving averages crossed
```

### strictly_increasing(series, lookback)

Checks if series has been strictly increasing.

**Parameters:**
- `series`: Series to check
- `lookback`: Number of periods to check

**Returns:** True if series increased every period

### strictly_decreasing(series, lookback)

Checks if series has been strictly decreasing.

**Parameters:**
- `series`: Series to check
- `lookback`: Number of periods to check

**Returns:** True if series decreased every period

### streaks(series, use_diff=True)

Calculates winning/losing streaks.

**Parameters:**
- `series`: Series of returns or P&L
- `use_diff`: Whether to use differences

**Returns:** Array of streak lengths

## Statistical Tools

### kelly_criterion(win_rate, ratio_avg_win_loss)

Calculates optimal position size using Kelly Criterion.

**Parameters:**
- `win_rate`: Win rate (0.6 = 60%)
- `ratio_avg_win_loss`: Average win divided by average loss

**Returns:** Optimal fraction of capital to risk (0.1 = 10%)

### z_score(series)

Calculates z-score (standard deviations from mean).

**Parameters:**
- `series`: Input series

**Returns:** Z-score series

### prices_to_returns(price_series)

Converts price series to returns.

**Parameters:**
- `price_series`: Array of prices

**Returns:** Array of returns

## Data Conversion

### numpy_candles_to_dataframe(candles, name_date="date", name_open="open", ...)

Converts numpy candle array to pandas DataFrame.

**Parameters:**
- `candles`: Numpy array of OHLCV data
- `name_date`: Column name for timestamp
- `name_open`: Column name for open price
- etc.

**Returns:** Pandas DataFrame

## Timeframe Utilities

### anchor_timeframe(timeframe)

Returns the anchor timeframe for multi-timeframe strategies.

**Parameters:**
- `timeframe`: Current timeframe string

**Returns:** Anchor timeframe string

**Example:**
```python
# For 5m timeframe, returns "30m"
# For 1h timeframe, returns "4h"
anchor = utils.anchor_timeframe("5m")  # Returns "30m"
```

### TIMEFRAME_TO_ONE_MINUTES

Convert timeframe strings to minutes for calculations.

```python
from jesse.constants import TIMEFRAME_TO_ONE_MINUTES

# Get minutes in each timeframe
minutes_1h = TIMEFRAME_TO_ONE_MINUTES['1h']  # 60
minutes_4h = TIMEFRAME_TO_ONE_MINUTES['4h']  # 240
minutes_1d = TIMEFRAME_TO_ONE_MINUTES['1D']  # 1440

# Useful for multi-timeframe position sizing
# Risk 2% per day regardless of timeframe
daily_risk = 0.02
timeframe_minutes = TIMEFRAME_TO_ONE_MINUTES[self.timeframe]
timeframe_risk = daily_risk * (timeframe_minutes / 1440)
```

### TIMEFRAME_PRIORITY

Timeframes ordered by length (longest to shortest).

```python
from jesse.constants import TIMEFRAME_PRIORITY

# ['1D', '12h', '8h', '6h', '4h', '3h', '2h', '1h', '45m', '30m', '15m', '5m', '3m', '1m']
# Useful for determining which timeframe to use as primary
primary_timeframe = TIMEFRAME_PRIORITY[0]  # '1D'
```

## Precision Helpers

### subtract_floats(float1, float2)

Subtracts floats with proper precision handling.

### sum_floats(float1, float2)

Adds floats with proper precision handling.

These functions help avoid floating-point precision issues common in financial calculations.