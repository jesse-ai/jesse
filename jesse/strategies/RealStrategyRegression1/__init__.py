# Real-world regression-test strategy. Adapted from the maintainer's bot project
# ("AlligatorV2") for regression testing: a multi-timeframe Alligator trend system
# with ADX/CMO/Stochastic-RSI filters and ATR-based stop-loss/take-profit.
# Adaptation notes: class renamed; dna() removed so the plain hyperparameter
# defaults below apply; position value is capped at 80% of margin*leverage so the
# aggressive sizing can never raise InsufficientMargin on the synthetic test data.
# The entry/exit logic is byte-for-byte the original.
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class RealStrategyRegression1(Strategy):
    @property
    def long_term_candles(self):
        # Get candles for a larger timeframe to analyze long-term trends
        big_tf = '4h'
        if self.timeframe == '4h':
            big_tf = '6h'
        return self.get_candles(self.exchange, self.symbol, big_tf)

    @property
    def adx(self):
        # Calculate the ADX (Average Directional Index) to determine trend strength
        return ta.adx(self.candles) > self.hp['adx_threshold']

    @property
    def cmo(self):
        # Calculate the CMO (Chande Momentum Oscillator) for momentum analysis
        return ta.cmo(self.candles, 14)

    @property
    def srsi(self):
        # Calculate the Stochastic RSI for overbought/oversold conditions
        return ta.srsi(self.candles).k

    @property
    def alligator(self):
        # Calculate the Alligator indicator for trend direction
        return ta.alligator(self.candles)

    @property
    def big_alligator(self):
        # Calculate the Alligator indicator on a larger timeframe for long-term trend direction
        return ta.alligator(self.long_term_candles)

    @property
    def trend(self):
        # Determine the current trend based on the Alligator indicator
        if self.price > self.alligator.lips > self.alligator.teeth > self.alligator.jaw:
            return 1  # Uptrend
        if self.price < self.alligator.lips < self.alligator.teeth < self.alligator.jaw:
            return -1  # Downtrend
        return 0  # No clear trend

    @property
    def big_trend(self):
        # Determine the long-term trend based on the Alligator indicator on a larger timeframe
        if self.price > self.big_alligator.lips > self.big_alligator.teeth > self.big_alligator.jaw:
            return 1  # Long-term uptrend
        if self.price < self.big_alligator.lips < self.big_alligator.teeth < self.big_alligator.jaw:
            return -1  # Long-term downtrend
        return 0  # No clear long-term trend

    @property
    def long_term_ma(self):
        # Calculate the 100-period EMA on a larger timeframe for long-term trend confirmation
        e = ta.ema(self.long_term_candles, self.hp['longterm_ema_period'])
        if self.price > e:
            return 1  # Price is above the EMA
        if self.price < e:
            return -1  # Price is below the EMA

    def should_long(self) -> bool:
        # Determine if conditions are met to enter a long position
        return self.trend == 1 and self.adx and self.big_trend == 1 and self.long_term_ma == 1 and self.cmo > self.hp['cmo_threshold'] and self.srsi < 20

    def should_short(self) -> bool:
        # Determine if conditions are met to enter a short position
        return self.trend == -1 and self.adx and self.big_trend == -1 and self.long_term_ma == -1 and self.cmo < -self.hp['cmo_threshold'] and self.srsi > 80

    def go_long(self):
        # Execute a long position
        entry = self.price
        stop = entry - ta.atr(self.candles) * 2  # Set stop loss based on ATR
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate) * 3  # Calculate position size
        # regression-test adaptation: cap position value at 80% of margin*leverage
        qty = min(qty, utils.size_to_qty(self.available_margin * self.leverage * 0.8, entry, fee_rate=self.fee_rate))
        self.buy = qty, entry  # Place buy market order

    def go_short(self):
        # Execute a short position
        entry = self.price
        stop = entry + ta.atr(self.candles) * 2  # Set stop loss based on ATR
        qty = utils.risk_to_qty(self.available_margin, 3, entry, stop, fee_rate=self.fee_rate) * 3  # Calculate position size
        # regression-test adaptation: cap position value at 80% of margin*leverage
        qty = min(qty, utils.size_to_qty(self.available_margin * self.leverage * 0.8, entry, fee_rate=self.fee_rate))
        self.sell = qty, entry  # Place sell market order

    def should_cancel_entry(self) -> bool:
        # Always cancel the entry if conditions are not met
        return True

    def on_open_position(self, order) -> None:
        # Set stop loss and take profit when a position is opened
        if self.is_long:
            self.stop_loss = self.position.qty, self.price - ta.atr(self.candles) * self.hp['stop_atr']
            self.take_profit = self.position.qty, self.price + ta.atr(self.candles) * self.hp['take_profit_atr']
        if self.is_short:
            self.stop_loss = self.position.qty, self.price + ta.atr(self.candles) * self.hp['stop_atr']
            self.take_profit = self.position.qty, self.price - ta.atr(self.candles) * self.hp['take_profit_atr']

    def hyperparameters(self) -> list:
        # Define the hyperparameters for the strategy
        return [
            {'name': 'stop_atr', 'type': float, 'min': 1.5, 'max': 3, 'default': 2},
            {'name': 'take_profit_atr', 'type': float, 'min': 1.5, 'max': 3, 'default': 2},
            {'name': 'adx_threshold', 'type': int, 'min': 1, 'max': 50, 'default': 30},
            {'name': 'longterm_ema_period', 'type': int, 'min': 100, 'max': 200, 'default': 100},
            {'name': 'cmo_threshold', 'type': int, 'min': 5, 'max': 50, 'default': 20},
        ]
