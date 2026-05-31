# Strategy examples

A library of complete, copy-pasteable Jesse strategies that demonstrate real,
verified API patterns: trend filters, ATR-based stops, partial take-profits,
trailing stops, lifecycle hooks, multi-timeframe candles, optimization
hyperparameters, live-monitoring watch lists, and multi-route pairs trading.

These are illustrative reference strategies, NOT financial advice. They exist to
show *how the API is used*, not to recommend any particular trading approach.
Treat parameter values (periods, multipliers, leverage factors) as placeholders
to tune, validate, and risk-check yourself.

For the strategy structure, the required/optional methods, smart-order routing,
spot-vs-futures exit rules, and the interactive-chart helpers, see
`jesse://strategy`. For sizing/exit reference and helper signatures, see
`jesse://position_risk` and `jesse://utilities`. This file intentionally does
not restate that material; it only collects worked classes.

Every class below is complete and starts with the canonical imports:

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils
```

---

## TrendFollowingAI — preparing a strategy for optimization

This pair shows the *before/after* of getting a strategy ready for Jesse's
optimization mode. A multi-timeframe trend follower (futures, long + short)
takes signals only when a 6h SMA stack and a base-timeframe SMA stack agree,
gated by MACD histogram and ADX. It sets ATR-based stop-loss and take-profit in
`on_open_position()` and exits early in `update_position()` when the fast/slow
SMA cross flips or MACD turns.

Features shown: multi-timeframe candles via `get_candles(self.exchange,
self.symbol, '6h')`, `macd.hist`, `adx`, `atr`, `size_to_qty` sizing with a
leverage multiplier, `on_open_position()`/`update_position()` hooks.

The plain version hardcodes every parameter:

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class TrendFollowingAI(Strategy):
    @property
    def longterm_small_ma(self):
        return ta.sma(self.candles_6h, 50)

    @property
    def longterm_big_ma(self):
        return ta.sma(self.candles_6h, 200)

    @property
    def small_ma(self):
        return ta.sma(self.candles, 20)

    @property
    def big_ma(self):
        return ta.sma(self.candles, 50)

    @property
    def macd(self):
        return ta.macd(self.candles)

    @property
    def adx(self):
        return ta.adx(self.candles)

    @property
    def atr(self):
        return ta.atr(self.candles)

    def should_long(self) -> bool:
        # Big-trend condition: bullish
        if self.longterm_small_ma > self.longterm_big_ma and self.small_ma > self.big_ma:
            # Entry signals: fast SMA above slow SMA, MACD histogram > 0, ADX > 40
            if self.small_ma > self.big_ma and self.macd.hist > 0 and self.adx > 40:
                return True
        return False

    def go_long(self):
        entry_price = self.price
        qty = utils.size_to_qty(self.balance, entry_price) * 3
        self.buy = qty, entry_price

    def should_short(self) -> bool:
        # Big-trend condition: bearish
        if self.longterm_small_ma < self.longterm_big_ma and self.small_ma < self.big_ma:
            if self.small_ma < self.big_ma and self.macd.hist < 0 and self.adx > 40:
                return True
        return False

    def go_short(self) -> None:
        entry_price = self.price
        qty = utils.size_to_qty(self.balance, entry_price) * 3
        self.sell = qty, entry_price

    def on_open_position(self, order):
        # Set stop-loss and take-profit using ATR (mirror the levels for shorts)
        if self.is_long:
            self.stop_loss = self.position.qty, self.price - self.atr * 1
            self.take_profit = self.position.qty, self.price + self.atr * 2
        elif self.is_short:
            self.stop_loss = self.position.qty, self.price + self.atr * 1
            self.take_profit = self.position.qty, self.price - self.atr * 2

    def update_position(self):
        # Early exit when the trend or momentum turns
        if self.small_ma < self.big_ma or self.macd.hist < 0:
            self.liquidate()

    def should_cancel_entry(self) -> bool:
        return False

    @property
    def candles_6h(self):
        return self.get_candles(self.exchange, self.symbol, '6h')
```

The prepared version replaces hardcoded numbers with `self.hp[...]` lookups and
declares `hyperparameters()`. Jesse fills `self.hp` from each parameter's
`default` (or decodes it from a `dna()` string), so the strategy still runs
unchanged in a normal backtest while becoming tunable in optimization mode. Each
hyperparameter dict needs `name`, `type`, `min`, `max`, `default` (`step` and
`options` are optional):

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class TrendFollowingAI(Strategy):
    @property
    def longterm_small_ma(self):
        return ta.sma(self.candles_6h, 50)

    @property
    def longterm_big_ma(self):
        return ta.sma(self.candles_6h, 200)

    @property
    def small_ma(self):
        return ta.sma(self.candles, self.hp['small_ma'])

    @property
    def big_ma(self):
        return ta.sma(self.candles, self.hp['big_ma'])

    @property
    def macd(self):
        return ta.macd(self.candles)

    @property
    def adx(self):
        return ta.adx(self.candles)

    @property
    def atr(self):
        return ta.atr(self.candles)

    def should_long(self) -> bool:
        if self.longterm_small_ma > self.longterm_big_ma and self.small_ma > self.big_ma:
            if self.small_ma > self.big_ma and self.macd.hist > 0 and self.adx > self.hp['adx_threshold']:
                return True
        return False

    def go_long(self):
        entry_price = self.price
        qty = utils.size_to_qty(self.balance, entry_price) * 3
        self.buy = qty, entry_price

    def should_short(self) -> bool:
        if self.longterm_small_ma < self.longterm_big_ma and self.small_ma < self.big_ma:
            if self.small_ma < self.big_ma and self.macd.hist < 0 and self.adx > self.hp['adx_threshold']:
                return True
        return False

    def go_short(self) -> None:
        entry_price = self.price
        qty = utils.size_to_qty(self.balance, entry_price) * 3
        self.sell = qty, entry_price

    def on_open_position(self, order):
        if self.is_long:
            self.stop_loss = self.position.qty, self.price - self.atr * self.hp['stop_loss_multiplier']
            self.take_profit = self.position.qty, self.price + self.atr * self.hp['take_profit_multiplier']
        elif self.is_short:
            self.stop_loss = self.position.qty, self.price + self.atr * self.hp['stop_loss_multiplier']
            self.take_profit = self.position.qty, self.price - self.atr * self.hp['take_profit_multiplier']

    def update_position(self):
        if self.small_ma < self.big_ma or self.macd.hist < 0:
            self.liquidate()

    def should_cancel_entry(self) -> bool:
        return False

    @property
    def candles_6h(self):
        return self.get_candles(self.exchange, self.symbol, '6h')

    def hyperparameters(self) -> list:
        return [
            {'name': 'stop_loss_multiplier', 'type': float, 'min': 0.5, 'max': 3, 'default': 1},
            {'name': 'take_profit_multiplier', 'type': float, 'min': 1, 'max': 5, 'default': 2},
            {'name': 'adx_threshold', 'type': int, 'min': 20, 'max': 60, 'default': 40},
            {'name': 'small_ma', 'type': int, 'min': 5, 'max': 50, 'default': 20},
            {'name': 'big_ma', 'type': int, 'min': 20, 'max': 100, 'default': 50},
        ]
```

---

## AlligatorAi — preparing a strategy for live monitoring with `watch_list()`

`watch_list()` returns a list of `(label, value)` tuples that Jesse surfaces in
the live/paper dashboard so you can watch the indicators driving the strategy in
real time. This Alligator-based futures strategy aligns a base-timeframe
Alligator, a higher-timeframe Alligator, a higher-timeframe EMA, ADX, CMO, and
Stochastic RSI before entering, sizes positions with `risk_to_qty`, and sets
symmetric ATR stop/target in `on_open_position()`.

Features shown: `watch_list()`, multi-timeframe candles with a timeframe swap,
`alligator` (`lips`/`teeth`/`jaw`), `srsi(...).k`, `cmo`, `adx`, `risk_to_qty`
sizing.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class AlligatorAi(Strategy):
    @property
    def long_term_candles(self):
        # Higher-timeframe candles for long-term trend analysis
        big_tf = '4h'
        if self.timeframe == '4h':
            big_tf = '6h'
        return self.get_candles(self.exchange, self.symbol, big_tf)

    @property
    def adx(self):
        # ADX > 30 confirms there is a trend worth trading
        return ta.adx(self.candles) > 30

    @property
    def cmo(self):
        # Chande Momentum Oscillator
        return ta.cmo(self.candles, 14)

    @property
    def srsi(self):
        # Stochastic RSI %K line
        return ta.srsi(self.candles).k

    @property
    def alligator(self):
        return ta.alligator(self.candles)

    @property
    def big_alligator(self):
        return ta.alligator(self.long_term_candles)

    @property
    def trend(self):
        # Base-timeframe trend from the Alligator
        if self.price > self.alligator.lips > self.alligator.teeth > self.alligator.jaw:
            return 1  # Uptrend
        if self.price < self.alligator.lips < self.alligator.teeth < self.alligator.jaw:
            return -1  # Downtrend
        return 0  # No clear trend

    @property
    def big_trend(self):
        # Higher-timeframe trend from the Alligator
        if self.price > self.big_alligator.lips > self.big_alligator.teeth > self.big_alligator.jaw:
            return 1
        if self.price < self.big_alligator.lips < self.big_alligator.teeth < self.big_alligator.jaw:
            return -1
        return 0

    @property
    def long_term_ma(self):
        # 100-period EMA on the higher timeframe for trend confirmation
        e = ta.ema(self.long_term_candles, 100)
        if self.price > e:
            return 1
        if self.price < e:
            return -1
        return 0

    def should_long(self) -> bool:
        return self.trend == 1 and self.adx and self.big_trend == 1 and self.long_term_ma == 1 and self.cmo > 20 and self.srsi < 20

    def should_short(self) -> bool:
        return self.trend == -1 and self.adx and self.big_trend == -1 and self.long_term_ma == -1 and self.cmo < -20 and self.srsi > 80

    def go_long(self):
        entry = self.price
        stop = entry - ta.atr(self.candles) * 2
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate) * 3
        self.buy = qty, entry

    def go_short(self):
        entry = self.price
        stop = entry + ta.atr(self.candles) * 2
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate) * 3
        self.sell = qty, entry

    def should_cancel_entry(self) -> bool:
        return True

    def on_open_position(self, order) -> None:
        if self.is_long:
            self.stop_loss = self.position.qty, self.price - ta.atr(self.candles) * 2
            self.take_profit = self.position.qty, self.price + ta.atr(self.candles) * 2
        if self.is_short:
            self.stop_loss = self.position.qty, self.price + ta.atr(self.candles) * 2
            self.take_profit = self.position.qty, self.price - ta.atr(self.candles) * 2

    def watch_list(self) -> list:
        return [
            ('trend', self.trend),
            ('big_trend', self.big_trend),
            ('long_term_ma', self.long_term_ma),
            ('adx', self.adx),
            ('cmo', self.cmo),
            ('srsi', self.srsi),
        ]
```

Note: do not put `self.buy`, `self.sell`, `self.take_profit`, or
`self.stop_loss` into `watch_list()`. Those attributes are write targets used to
*submit* orders — reading them back does not give you the live order, and after
normalization they are 2D order arrays, not plain `(qty, price)` tuples. Watch
the indicator/derived values that drive your decisions instead.

---

## Example 1 — GoldenCross

A minimal EMA20/EMA50 trend follower (spot-style, long only). It opens with half
the balance, takes partial profit on half the position, and after that partial
fill tightens the stop in `update_position()` using a candle-range trailing
rule; it also flat-exits when the trend flips.

Features shown: partial take-profit (`self.position.qty / 2`), `reduced_count`
to detect that the partial filled, a candle-range-based trailing stop, and an
optional `filters()` entry gate.

> `filters()` is optional. A filter is a method (referenced, not called) that
> returns a bool; the entry is allowed only if every filter passes. Skip it
> unless you actually need an extra gate.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class GoldenCross(Strategy):
    @property
    def ema20(self):
        return ta.ema(self.candles, 20)

    @property
    def ema50(self):
        return ta.ema(self.candles, 50)

    @property
    def trend(self):
        if self.ema20 > self.ema50:
            return 1  # Uptrend
        else:
            return -1  # Downtrend

    def should_long(self) -> bool:
        return self.trend == 1

    def go_long(self):
        entry_price = self.price
        qty = utils.size_to_qty(self.balance * 0.5, entry_price)
        self.buy = qty, entry_price  # MARKET order (price == current price)

    def update_position(self) -> None:
        if self.reduced_count == 1:
            # Partial take-profit already filled: trail the stop one range below price
            self.stop_loss = self.position.qty, self.price - self.current_range
        elif self.trend == -1:
            self.liquidate()  # Close with a MARKET order

    @property
    def current_range(self):
        return self.high - self.low

    def on_open_position(self, order) -> None:
        self.stop_loss = self.position.qty, self.price - self.current_range * 2
        self.take_profit = self.position.qty / 2, self.price + self.current_range * 2

    def should_cancel_entry(self) -> bool:
        return True

    def filters(self) -> list:
        return [
            self.rsi_filter
        ]

    def rsi_filter(self):
        rsi = ta.rsi(self.candles)
        return rsi < 65
```

---

## Example 2 — TrendSwingTrader

A stacked-EMA swing strategy (futures, long + short). It requires a clean
21/50/100 EMA stack relative to price plus ADX > 25, sizes with `risk_to_qty`,
takes partial profit, then in `on_reduced_position()` moves the stop to
breakeven (entry price) and in `update_position()` trails it once the partial
has filled.

Features shown: risk-based sizing, partial take-profit, `on_reduced_position()`
breakeven move, `reduced_count` + `position.entry_price` trailing.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class TrendSwingTrader(Strategy):
    @property
    def adx(self):
        return ta.adx(self.candles) > 25

    @property
    def trend(self):
        e1 = ta.ema(self.candles, 21)
        e2 = ta.ema(self.candles, 50)
        e3 = ta.ema(self.candles, 100)
        if e3 < e2 < e1 < self.price:
            return 1
        elif e3 > e2 > e1 > self.price:
            return -1
        else:
            return 0

    def should_long(self) -> bool:
        return self.trend == 1 and self.adx

    def go_long(self):
        entry = self.price
        stop = entry - ta.atr(self.candles) * 2
        qty = utils.risk_to_qty(self.available_margin, 5, entry, stop, fee_rate=self.fee_rate) * 2
        self.buy = qty, entry

    def should_short(self) -> bool:
        return self.trend == -1 and self.adx

    def go_short(self):
        entry = self.price
        stop = entry + ta.atr(self.candles) * 2
        qty = utils.risk_to_qty(self.available_margin, 5, entry, stop, fee_rate=self.fee_rate) * 2
        self.sell = qty, entry

    def should_cancel_entry(self) -> bool:
        return True

    def on_open_position(self, order) -> None:
        if self.is_long:
            self.stop_loss = self.position.qty, self.price - ta.atr(self.candles) * 2
            self.take_profit = self.position.qty / 2, self.price + ta.atr(self.candles) * 3
        elif self.is_short:
            self.stop_loss = self.position.qty, self.price + ta.atr(self.candles) * 2
            self.take_profit = self.position.qty / 2, self.price - ta.atr(self.candles) * 3

    def on_reduced_position(self, order) -> None:
        # After the partial take-profit fills, move the stop to breakeven
        if self.is_long:
            self.stop_loss = self.position.qty, self.position.entry_price
        elif self.is_short:
            self.stop_loss = self.position.qty, self.position.entry_price

    def update_position(self) -> None:
        if self.reduced_count == 1:
            if self.is_long:
                self.stop_loss = self.position.qty, max(self.price - ta.atr(self.candles) * 2, self.position.entry_price)
            elif self.is_short:
                self.stop_loss = self.position.qty, min(self.price + ta.atr(self.candles) * 2, self.position.entry_price)
```

---

## Example 3 — SimpleBollinger

A Bollinger-band breakout (spot-style, long only) that uses `hl2` as the band
source and an Ichimoku-cloud trend filter. It buys when the candle closes above
the upper band and is above both cloud spans, then exits when price closes back
below the middle band.

Features shown: `bollinger_bands(..., source_type="hl2")` and indexing the
returned namedtuple (`bb[0]` = upper, `bb[1]` = middle), `ichimoku_cloud`
(`span_a`/`span_b`) as a filter, `should_short` returning `False` for a
single-side strategy.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class SimpleBollinger(Strategy):
    @property
    def bb(self):
        # Bollinger Bands with default parameters and hl2 as the source
        return ta.bollinger_bands(self.candles, source_type="hl2")

    @property
    def ichimoku(self):
        return ta.ichimoku_cloud(self.candles)

    def filter_trend(self):
        # Only go long when close is above the Ichimoku cloud
        return self.close > self.ichimoku.span_a and self.close > self.ichimoku.span_b

    def filters(self):
        return [self.filter_trend]

    def should_long(self) -> bool:
        # Close above the upper band
        return self.close > self.bb[0]

    def should_short(self) -> bool:
        return False

    def should_cancel_entry(self) -> bool:
        return True

    def go_long(self):
        qty = utils.size_to_qty(self.balance, self.price, fee_rate=self.fee_rate)
        self.buy = qty, self.price

    def go_short(self):
        pass

    def update_position(self):
        # Close when price falls back below the middle band
        if self.close < self.bb[1]:
            self.liquidate()
```

---

## Example 4 — Donchian

A Donchian-channel breakout (spot-style, long only) with a 200-SMA trend filter.
It reads the *previous* channel by slicing off the forming candle
(`self.candles[:-1]`) so the breakout level is the completed channel, buys on a
close above the upper band, and exits on a close below the lower band.

Features shown: `donchian` (`upperband`/`lowerband`), the `self.candles[:-1]`
previous-channel idiom, a `period=` keyword on an indicator call.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class Donchian(Strategy):
    @property
    def donchian(self):
        # Previous Donchian channel (exclude the forming candle)
        return ta.donchian(self.candles[:-1])

    @property
    def ma_trend(self):
        return ta.sma(self.candles, period=200)

    def filter_trend(self):
        # Only go long when close is above the 200 SMA
        return self.close > self.ma_trend

    def filters(self):
        return [self.filter_trend]

    def should_long(self) -> bool:
        return self.close > self.donchian.upperband

    def should_short(self) -> bool:
        return False

    def should_cancel_entry(self) -> bool:
        return True

    def go_long(self):
        qty = utils.size_to_qty(self.balance, self.price, fee_rate=self.fee_rate)
        self.buy = qty, self.price

    def go_short(self):
        pass

    def update_position(self):
        if self.close < self.donchian.lowerband:
            self.liquidate()
```

---

## Example 5 — IchimokuCloud

A two-condition Ichimoku trend strategy (futures, long + short). It needs the
conversion/base-line cross and the cloud (`span_a` vs `span_b`) to agree,
filtered by ADX > 50 and Choppiness < 50. It enters with a limit order one ATR
better than price, sizes with `risk_to_qty` on 4x margin, anchors the stop to
`position.entry_price`, and exits when the short-term trend flips.

Features shown: `ichimoku_cloud` (`conversion_line`/`base_line`/`span_a`/
`span_b`), `chop`/`adx` confluence, limit entry below/above price, ATR stop off
`position.entry_price`.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class IchimokuCloud(Strategy):
    @property
    def small_trend(self):
        c = ta.ichimoku_cloud(self.candles)
        if c.conversion_line > c.base_line:
            return 1
        else:
            return -1

    @property
    def big_trend(self):
        c = ta.ichimoku_cloud(self.candles)
        if c.span_a > c.span_b:
            return 1
        else:
            return -1

    @property
    def adx(self):
        return ta.adx(self.candles) > 50

    @property
    def chop(self):
        return ta.chop(self.candles) < 50

    def should_long(self) -> bool:
        return self.small_trend == 1 and self.big_trend == 1 and self.adx and self.chop

    def should_short(self) -> bool:
        return self.small_trend == -1 and self.big_trend == -1 and self.adx and self.chop

    def go_long(self):
        entry = self.price - ta.atr(self.candles)
        stop = entry - ta.atr(self.candles) * 2.5
        qty = utils.risk_to_qty(self.available_margin * 4, 3, entry, stop, fee_rate=self.fee_rate)
        self.buy = qty, entry

    def go_short(self):
        entry = self.price + ta.atr(self.candles)
        stop = entry + ta.atr(self.candles) * 2.5
        qty = utils.risk_to_qty(self.available_margin * 4, 3, entry, stop, fee_rate=self.fee_rate)
        self.sell = qty, entry

    def should_cancel_entry(self) -> bool:
        return True

    def on_open_position(self, order) -> None:
        if self.is_long:
            self.stop_loss = self.position.qty, self.position.entry_price - ta.atr(self.candles) * 2.5
        elif self.is_short:
            self.stop_loss = self.position.qty, self.position.entry_price + ta.atr(self.candles) * 2.5

    def update_position(self) -> None:
        if self.is_long:
            if self.small_trend == -1:
                self.liquidate()
        elif self.is_short:
            if self.small_trend == 1:
                self.liquidate()
```

---

## Example 6 — TurtleAI

A Turtle-style Donchian breakout (futures, long + short) over a 4h trend filter,
with a cooldown gate and an ATR trailing stop. It demonstrates a class-level
attribute (`last_closed_index`) updated from `on_close_position()` to enforce a
"wait one bar after a close" rule, draws the channel on the chart in `after()`,
and ratchets the stop using `self.average_stop_loss`.

Features shown: class-level state, `passed_time` cooldown via `self.index`,
`donchian` breakout, ATR trailing with `self.average_stop_loss` (read the
current stop — never index `self.stop_loss[1]`), `after()` +
`add_line_to_candle_chart`, and the **two-argument** `on_close_position(order,
closed_trade)` hook.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class TurtleAI(Strategy):
    last_closed_index = 0

    @property
    def long_term_candles(self):
        return self.get_candles(self.exchange, self.symbol, '4h')

    @property
    def passed_time(self):
        return self.index - self.last_closed_index > 0

    @property
    def longterm_ma(self):
        return ta.sma(self.long_term_candles, 200)

    @property
    def adx(self):
        return ta.adx(self.candles) > 30

    @property
    def chop(self):
        return ta.chop(self.candles) < 40

    @property
    def donchian(self):
        return ta.donchian(self.candles[:-1], period=20)

    def should_long(self) -> bool:
        return self.price > self.donchian.upperband and self.price > self.longterm_ma and self.adx and self.passed_time and self.chop

    def go_long(self):
        entry = self.price
        stop = self.price - ta.atr(self.candles) * 2.5
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate) * 1.8
        self.buy = qty, entry

    def should_short(self) -> bool:
        return self.price < self.donchian.lowerband and self.price < self.longterm_ma and self.adx and self.passed_time and self.chop

    def go_short(self):
        entry = self.price
        stop = self.price + ta.atr(self.candles) * 2.5
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate) * 1.8
        self.sell = qty, entry

    def should_cancel_entry(self) -> bool:
        return True

    def on_open_position(self, order) -> None:
        if self.is_long:
            self.stop_loss = self.position.qty, self.price - ta.atr(self.candles) * 2.5
        elif self.is_short:
            self.stop_loss = self.position.qty, self.price + ta.atr(self.candles) * 2.5

    def update_position(self) -> None:
        # ATR trailing stop: ratchet using the current (average) stop
        if self.is_long:
            self.stop_loss = self.position.qty, max(self.average_stop_loss, self.price - ta.atr(self.candles) * 2.5)
        elif self.is_short:
            self.stop_loss = self.position.qty, min(self.average_stop_loss, self.price + ta.atr(self.candles) * 2.5)

    def after(self) -> None:
        self.add_line_to_candle_chart('upperband', self.donchian.upperband)
        self.add_line_to_candle_chart('lowerband', self.donchian.lowerband)

    def on_close_position(self, order, closed_trade) -> None:
        self.last_closed_index = self.index
```

---

## Example 7 — K1

A KAMA-trend strategy (futures, long + short) requiring agreement between a
base-timeframe and a higher-timeframe KAMA trend, plus an ADX / Choppiness /
Bollinger-band-width "squeeze" confluence, with a per-trade cooldown counted in
bars. It sizes with `risk_to_qty` and sets symmetric ATR stop/target in
`on_open_position()`.

Features shown: `kama` trend, multi-timeframe with a timeframe swap, ADX/chop
filters, `bollinger_bands_width(...) * 100 < 7` squeeze gate, class-level
`last_trade_index` cooldown updated in the two-argument `on_close_position(order,
closed_trade)` hook.

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class K1(Strategy):
    last_trade_index = 0

    @property
    def long_term_candles(self):
        big_tf = '4h'
        if self.timeframe == '4h':
            big_tf = '6h'
        return self.get_candles(self.exchange, self.symbol, big_tf)

    @property
    def kama(self):
        return ta.kama(self.candles)

    @property
    def kama_trend(self):
        k = ta.kama(self.candles)
        if self.price > k:
            return 1
        else:
            return -1

    @property
    def big_kama_trend(self):
        k = ta.kama(self.long_term_candles)
        if self.price > k:
            return 1
        else:
            return -1

    @property
    def atr(self):
        return ta.atr(self.candles)

    @property
    def adx(self):
        return ta.adx(self.candles) > 50

    @property
    def chop(self):
        return ta.chop(self.candles) < 50

    @property
    def bbw(self):
        return ta.bollinger_bands_width(self.candles) * 100 < 7

    def should_long(self) -> bool:
        return (self.adx and
                self.kama_trend == 1 and
                self.big_kama_trend == 1 and
                self.index - self.last_trade_index > 10 and
                self.chop and
                self.bbw
                )

    def should_short(self) -> bool:
        return (self.adx and
                self.kama_trend == -1 and
                self.big_kama_trend == -1 and
                self.index - self.last_trade_index > 10 and
                self.chop and
                self.bbw
                )

    def go_long(self):
        entry = self.price
        stop = self.price - ta.atr(self.candles) * 2.5
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate)
        self.buy = qty, self.price

    def go_short(self):
        entry = self.price
        stop = self.price + ta.atr(self.candles) * 2.5
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate)
        self.sell = qty, self.price

    def on_open_position(self, order):
        if self.is_long:
            self.stop_loss = self.position.qty, self.price - (self.atr * 2.5)
            self.take_profit = self.position.qty, self.price + (self.atr * 2.5)
        elif self.is_short:
            self.stop_loss = self.position.qty, self.price + (self.atr * 2.5)
            self.take_profit = self.position.qty, self.price - (self.atr * 2.5)

    def on_close_position(self, order, closed_trade) -> None:
        self.last_trade_index = self.index
```

---

## Example 8 — PairsTrading (multi-route)

A pairs-trading strategy spans at least two routes. One route **leads**: it does
all the math (returns, cointegration test, z-score of the spread) and writes the
decisions into `self.shared_vars` so the other routes can read them. The other
routes are tiny **followers** that just read `shared_vars` and go long, short, or
flat.

`self.shared_vars` is a dict shared across every route in the run, which is how
the routes coordinate. The leading route also splits available margin between the
two legs using a beta weighting from `utils.calculate_alpha_beta`.

Features shown: `self.routes[i].symbol`, `get_candles(...)[:, 2]` to read the
close column, `utils.prices_to_returns` / `utils.z_score` /
`utils.are_cointegrated` / `utils.calculate_alpha_beta` /
`utils.timeframe_to_one_minutes`, cross-route coordination via
`self.shared_vars`, and a periodic re-check in `before()`.

Leading route:

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class PairsTrading(Strategy):
    @property
    def c1(self):
        return utils.prices_to_returns(
            self.get_candles(self.exchange, self.routes[0].symbol, self.timeframe)[:, 2][-200:]
        )

    @property
    def c2(self):
        return utils.prices_to_returns(
            self.get_candles(self.exchange, self.routes[1].symbol, self.timeframe)[:, 2][-200:]
        )

    @property
    def z_score(self):
        spread = self.c1[1:] - self.c2[1:]
        z_scores = utils.z_score(spread)
        return z_scores[-1]

    def before(self) -> None:
        if self.index == 0:
            self.shared_vars["s1-position"] = 0
            self.shared_vars["s2-position"] = 0

        # Re-check cointegration roughly every 24 hours
        if self.index == 0 or self.index % (24 * 60 / utils.timeframe_to_one_minutes(self.timeframe)) == 0:
            is_cointegrated = utils.are_cointegrated(self.c1[1:], self.c2[1:])
            if not is_cointegrated:
                self.shared_vars["s1-position"] = 0
                self.shared_vars["s2-position"] = 0

        z_scores = self.z_score
        if self.is_close and z_scores < -1.2:
            self.shared_vars["s1-position"] = 1
            self.shared_vars["s2-position"] = -1
            self._set_proper_margin_per_route()
        elif self.is_long and z_scores > 0:
            self.shared_vars["s1-position"] = 0
            self.shared_vars["s2-position"] = 0
        elif self.is_short and z_scores < 0:
            self.shared_vars["s1-position"] = 0
            self.shared_vars["s2-position"] = 0
        elif self.is_close and z_scores > 1.2:
            self.shared_vars["s1-position"] = -1
            self.shared_vars["s2-position"] = 1
            self._set_proper_margin_per_route()

    def _set_proper_margin_per_route(self):
        _, beta = utils.calculate_alpha_beta(self.c1[1:], self.c2[1:])
        self.shared_vars["margin1"] = self.available_margin * (1 / (1 + beta))
        self.shared_vars["margin2"] = self.available_margin * (beta / (1 + beta))

    def should_long(self) -> bool:
        return self.shared_vars["s1-position"] == 1

    def should_short(self) -> bool:
        return self.shared_vars["s1-position"] == -1

    def go_long(self):
        qty = utils.size_to_qty(self.shared_vars["margin1"], self.price, fee_rate=self.fee_rate)
        self.buy = qty, self.price

    def go_short(self):
        qty = utils.size_to_qty(self.shared_vars["margin1"], self.price, fee_rate=self.fee_rate)
        self.sell = qty, self.price

    def update_position(self):
        if self.shared_vars["s1-position"] == 0:
            self.liquidate()
```

Following route — reads the `shared_vars` keys set by the leading route and
mirrors them (`margin2`, `s2-position`):

```py
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class PairsTrading2(Strategy):
    def should_long(self) -> bool:
        return self.shared_vars["s2-position"] == 1

    def should_short(self) -> bool:
        return self.shared_vars["s2-position"] == -1

    def go_long(self):
        qty = utils.size_to_qty(self.shared_vars["margin2"], self.price, fee_rate=self.fee_rate)
        self.buy = qty, self.price

    def go_short(self):
        qty = utils.size_to_qty(self.shared_vars["margin2"], self.price, fee_rate=self.fee_rate)
        self.sell = qty, self.price

    def update_position(self):
        if self.shared_vars["s2-position"] == 0:
            self.liquidate()
```
