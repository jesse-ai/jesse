from jesse.strategies import Strategy


class TestHoldingPeriodOfOpenTrade(Strategy):
    """
    Verifies ClosedTrade.holding_period for an OPEN trade (measured up to the
    current sim time) as well as the closed case.

    Up-trend backtest (prices 1..99, 1m). Enter long at 10, take profit at 20, so
    the position stays open for several 1m candles. While it is open we assert the
    live holding_period; on close we assert the finalized holding_period.
    """

    def before(self) -> None:
        # when flat, there is no current trade
        if not self.position.is_open:
            assert self.current_trade is None

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        if self.price == 10:
            self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = 1, 20  # keep it open for ~10 candles, then close

    def update_position(self) -> None:
        # fires every candle while the position is open
        t = self.current_trade
        assert t is not None, "current_trade must exist while a position is open"

        hp = t.holding_period
        assert hp is not None, "open trade holding_period must not be None"
        # the new behaviour: measured up to the current simulation time
        assert round(hp, 8) == round((self.time - t.opened_at) / 1000, 8)
        assert hp >= 0

        # 1m candles are 60s apart, so holding_period grows by exactly 60s/candle
        prev = getattr(self, '_prev_hp', None)
        if prev is not None:
            assert hp >= prev
            assert round(hp - prev, 8) == 60.0
        self._prev_hp = hp
        if hp > 0:
            self._open_verified = True

    def on_close_position(self, order, closed_trade) -> None:
        # the open-trade path must actually have been exercised
        assert getattr(self, '_open_verified', False), "open holding_period path never ran"
        # closed case: closed_at - opened_at
        assert closed_trade.closed_at is not None
        assert round(closed_trade.holding_period, 8) == \
            round((closed_trade.closed_at - closed_trade.opened_at) / 1000, 8)
        assert closed_trade.holding_period > 0
