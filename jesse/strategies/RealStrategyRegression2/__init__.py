# Real-world regression-test strategy. Adapted from the maintainer's bot project
# ("DonchianATRTrend") for regression testing: Donchian-channel breakouts filtered
# by a 4h SMA-200 trend and an ATR-expansion gate, with ATR-multiple SL/TP and a
# Donchian trailing stop. Adaptations: class renamed; position value capped at 80%
# of margin*leverage so sizing can never raise InsufficientMargin on the synthetic
# test data. The entry/exit logic is byte-for-byte the original.
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class RealStrategyRegression2(Strategy):
    @property
    def donchian(self):
        # Use previous candles so channel doesn't use current candle's price for breakout detection
        return ta.donchian(self.candles[:-1], period=30)

    @property
    def atr(self):
        # current ATR (default period)
        return ta.atr(self.candles)

    @property
    def atr_sma(self):
        # 20-period SMA of ATR computed from ATR series
        atr_seq = ta.atr(self.candles, sequential=True)
        # safe average for cases with fewer than 20 values
        return ta.sma(atr_seq, period=20)

    @property
    def sma_4h(self):
        # long-term 4h SMA200 for trend direction
        c = self.get_candles(self.exchange, self.symbol, '4h')
        return ta.sma(c, 200)

    def should_long(self) -> bool:
        return (self.price > self.donchian.upperband
                and self.price > self.sma_4h
                and self.atr > self.atr_sma)

    def should_short(self) -> bool:
        return (self.price < self.donchian.lowerband
                and self.price < self.sma_4h
                and self.atr > self.atr_sma)

    def go_long(self) -> None:
        entry = self.price
        stop = entry - 5 * self.atr
        qty = utils.risk_to_qty(self.available_margin, 2, entry, stop, fee_rate=self.fee_rate)
        # regression-test adaptation: cap position value at 80% of margin*leverage
        qty = min(qty, utils.size_to_qty(self.available_margin * self.leverage * 0.8, entry, fee_rate=self.fee_rate))
        self.buy = qty, entry  # enter at current price

    def go_short(self) -> None:
        entry = self.price
        stop = entry + 5 * self.atr
        qty = utils.risk_to_qty(self.available_margin, 2, entry, stop, fee_rate=self.fee_rate)
        # regression-test adaptation: cap position value at 80% of margin*leverage
        qty = min(qty, utils.size_to_qty(self.available_margin * self.leverage * 0.8, entry, fee_rate=self.fee_rate))
        self.sell = qty, entry  # enter at current price

    def on_open_position(self, order) -> None:
        # set fixed stop loss and take profit on open using ATR multiples
        if self.is_long:
            sl = self.position.entry_price - 5 * self.atr
            tp = self.position.entry_price + 10 * self.atr
            self.stop_loss = self.position.qty, sl
            self.take_profit = self.position.qty, tp
        elif self.is_short:
            sl = self.position.entry_price + 5 * self.atr
            tp = self.position.entry_price - 10 * self.atr
            self.stop_loss = self.position.qty, sl
            self.take_profit = self.position.qty, tp

    def update_position(self) -> None:
        # Trail stop using Donchian channel without widening the prior stop
        # For longs: move stop up toward Donchian lower band but never set it lower than previous average stop
        if self.is_long:
            # candidate is donchian lower band (tighten stop if it's higher)
            new_stop = max(self.average_stop_loss, self.donchian.lowerband)
            # ensure we only move stop (qty required)
            self.stop_loss = self.position.qty, new_stop

        # For shorts: move stop down toward Donchian upper band but never set it higher than previous average stop
        elif self.is_short:
            new_stop = min(self.average_stop_loss, self.donchian.upperband)
            self.stop_loss = self.position.qty, new_stop
