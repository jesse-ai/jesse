"""
Golden Cross Strategy
A simple strategy that uses EMA crossover to determine entry/exit signals.
"""
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class GoldenCross(Strategy):
    """
    Golden Cross Strategy:
    - Go long when EMA 8 crosses above EMA 21
    - Exit when EMA 8 crosses below EMA 21
    """

    def should_long(self) -> bool:
        # Go long when fast EMA crosses above slow EMA
        return self.fast_ema > self.slow_ema

    def should_short(self) -> bool:
        # Go short when fast EMA crosses below slow EMA
        return self.fast_ema < self.slow_ema

    def go_long(self):
        # Calculate position size (5% of balance)
        qty = utils.size_to_qty(self.balance * 0.05, self.price)
        self.buy = qty, self.price
        # Set stop loss at 5% below entry
        self.stop_loss = qty, self.price * 0.95
        # Set take profit at 10% above entry
        self.take_profit = qty, self.price * 1.10

    def go_short(self):
        # Calculate position size (5% of balance)
        qty = utils.size_to_qty(self.balance * 0.05, self.price)
        self.sell = qty, self.price
        # Set stop loss at 5% above entry
        self.stop_loss = qty, self.price * 1.05
        # Set take profit at 10% below entry
        self.take_profit = qty, self.price * 0.90

    def should_cancel_entry(self):
        return False

    @property
    def fast_ema(self):
        return ta.ema(self.candles, self.hp['fast_period'])

    @property
    def slow_ema(self):
        return ta.ema(self.candles, self.hp['slow_period'])

    def hyperparameters(self):
        """
        Define hyperparameters that can be optimized.
        """
        return [
            {'name': 'fast_period', 'type': int, 'min': 5, 'max': 20, 'default': 8},
            {'name': 'slow_period', 'type': int, 'min': 15, 'max': 50, 'default': 21},
        ]

    def filters(self):
        return []
