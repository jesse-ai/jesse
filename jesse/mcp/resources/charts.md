# Strategy Charts

Use Jesse's strategy chart API to visualize indicators and reference levels on
interactive backtest, paper-trading, and live-trading charts.

## Workflow for Adding Charts to a Strategy

1. Read the existing strategy with `read_strategy()`.
2. Add chart code to its existing `update_chart()` method, or create that method
   if it does not exist. Never define `update_chart()` twice.
3. Preserve all trading logic. Chart requests should only change visualization
   code unless the user explicitly asks for strategy changes too.
4. Save the complete updated strategy with `write_strategy()`.

Choose the method from the value being displayed:

| What to display | Method |
| --- | --- |
| EMA, Supertrend, or another price-scale indicator | `add_line_to_candle_chart(...)` |
| Support, resistance, or another fixed price | `add_horizontal_line_to_candle_chart(...)` |
| RSI, ADX, MACD, or another separate-scale indicator | `add_extra_line_chart(...)` |
| A fixed threshold inside an indicator pane | `add_horizontal_line_to_extra_chart(...)` |

## Where Chart Code Belongs

Put chart-only calculations in `update_chart()`:

```python
def update_chart(self) -> None:
    self.add_line_to_candle_chart(
        'ema50',
        ta.ema(self.candles, 50),
        color='blue',
    )
```

The framework calls this hook:

- once per completed candle in backtests, after the strategy logic; and
- approximately once per second in live and paper sessions, using the current
  forming candle.

In live and paper sessions, repeated updates for the same candle timestamp
replace that candle's most recent point. They do not append duplicate points.
When the next candle begins, Jesse appends a new point.

`update_chart()` must be visualization-only. Do not submit or cancel orders,
liquidate positions, send notifications, or mutate strategy state from this
hook. Trading decisions belong in the normal strategy lifecycle methods.

Chart calls made from `before()` or `after()` still work, but in live and paper
sessions they only run when the strategy itself executes for a completed route
candle. Use `update_chart()` when the current forming value must move intrabar.

## Chart Hook Example

Add this method to an otherwise complete strategy:

```python
from jesse.strategies import Strategy
import jesse.indicators as ta


class ChartDemo(Strategy):
    def update_chart(self) -> None:
        self.add_line_to_candle_chart(
            'ema50',
            ta.ema(self.candles, 50),
            color='blue',
        )
        self.add_horizontal_line_to_candle_chart(
            'support',
            60000,
            color='green',
            line_style='dotted',
        )

        self.add_extra_line_chart(
            'ADX',
            'adx14',
            ta.adx(self.candles, 14),
            color='orange',
        )
        self.add_extra_line_chart(
            'ADX',
            'adx21',
            ta.adx(self.candles, 21),
            color='blue',
        )
        self.add_horizontal_line_to_extra_chart(
            'ADX',
            'threshold',
            25,
            color='red',
        )
```

## API Reference

### Main candle chart

Use a candle-chart line for indicators that share the instrument's price scale,
such as moving averages or Bollinger Bands:

```python
self.add_line_to_candle_chart(title, value, color=None)
```

Use a horizontal candle-chart line for a fixed price level:

```python
self.add_horizontal_line_to_candle_chart(
    title,
    value,
    color=None,
    line_width=1.5,
    line_style='solid',
)
```

### Separate indicator panes

Use an extra chart when the indicator has a different scale from price, such as
RSI, ADX, or volume:

```python
self.add_extra_line_chart(chart_name, title, value, color=None)
```

Lines with the same `chart_name` share one pane. Use a horizontal extra-chart
line for thresholds such as RSI 70 or ADX 25:

```python
self.add_horizontal_line_to_extra_chart(
    chart_name,
    title,
    value,
    color=None,
    line_width=1.5,
    line_style='solid',
)
```

For both horizontal-line methods, `line_style` must be either `'solid'` or
`'dotted'`.

## Naming and Updating

- Keep `title` stable across calls. The title identifies one series or one
  horizontal level; changing it creates another item.
- Keep `chart_name` stable to group extra lines in the same pane.
- Pass the current finite numeric value, not a sequential indicator array.
- A horizontal line with an existing title is updated rather than duplicated.
- When an indicator returns a structured result, pass its current numeric field,
  such as `macd.macd`, rather than the complete result object.

## Live History Behavior

- Each live chart line retains its latest 1,000 candle points. Backtests keep
  their full chart history.
- Warm-up candles make indicators ready immediately, but their historical
  values are not replayed into a newly started live chart.
- Therefore, a new live session begins with the current forming value. Future
  candles build the visible indicator history naturally.
- Reloading the dashboard hydrates the accumulated chart snapshot for the
  running session.

## Dashboard Behavior

- Indicator values are shown in chart legends instead of as permanent
  right-scale labels.
- Clicking a main-chart indicator's legend name toggles that line.
- Extra indicator panes can be collapsed, and their latest values remain in the
  pane header.
- Order and strategy-defined horizontal price levels remain visible separately
  from indicator series.
