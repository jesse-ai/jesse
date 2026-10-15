# Real-world regression-test strategy. Adapted from the maintainer's bot project
# ("ADXTrendStrategy") for regression testing: ADX/DI trend strength with a
# Williams %R timing filter, SMA-50 stop, 30-bar extreme take-profit, and
# signal-flip liquidation. Adaptations: class renamed; position value capped at 80%
# of margin*leverage so sizing (whose stop distance can get arbitrarily small) can
# never raise InsufficientMargin on the synthetic test data. The entry/exit logic
# is byte-for-byte the original.
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class RealStrategyRegression3(Strategy):
    @property
    def adx(self):
        return ta.adx(self.candles)

    @property
    def di(self):
        return ta.di(self.candles)

    @property
    def williams_r(self):
        return ta.willr(self.candles)

    @property
    def sma50(self):
        return ta.sma(self.candles, 50)

    @property
    def highest_high(self):
        return max(self.candles[-30:, 3])

    @property
    def lowest_low(self):
        return min(self.candles[-30:, 4])

    def should_long(self) -> bool:
        # Long if DI+ > DI-, ADX > 50, and Williams %R < -80 (oversold)
        return (self.di.plus > self.di.minus and
                self.adx > 50 and
                self.williams_r < -80)

    def should_short(self) -> bool:
        # Short if DI+ < DI-, ADX > 50, and Williams %R > -20 (overbought)
        return (self.di.plus < self.di.minus and
                self.adx > 50 and
                self.williams_r > -20)

    def go_long(self):
        entry_price = self.price
        stop_loss = self.sma50
        qty = utils.risk_to_qty(self.available_margin, 3, entry_price, stop_loss, fee_rate=self.fee_rate)
        # regression-test adaptation: cap position value at 80% of margin*leverage
        qty = min(qty, utils.size_to_qty(self.available_margin * self.leverage * 0.8, entry_price, fee_rate=self.fee_rate))
        self.buy = qty, entry_price

    def go_short(self):
        entry_price = self.price
        stop_loss = self.sma50
        qty = utils.risk_to_qty(self.available_margin, 3, entry_price, stop_loss, fee_rate=self.fee_rate)
        # regression-test adaptation: cap position value at 80% of margin*leverage
        qty = min(qty, utils.size_to_qty(self.available_margin * self.leverage * 0.8, entry_price, fee_rate=self.fee_rate))
        self.sell = qty, entry_price

    def on_open_position(self, order):
        if self.is_long:
            self.stop_loss = self.position.qty, self.sma50
            self.take_profit = self.position.qty, self.highest_high
        elif self.is_short:
            self.stop_loss = self.position.qty, self.sma50
            self.take_profit = self.position.qty, self.lowest_low

    def update_position(self):
        if self.is_long and self.should_short():
            self.liquidate()
        elif self.is_short and self.should_long():
            self.liquidate()
