from jesse.strategies import Strategy


# test_is_smart_enough_to_open_positions_via_stop_orders
class Test06(Strategy):
    def should_long(self):
        """A failing trade that gets closed with the stopLoss order."""
        return self.time == 1547200740000 + 60_000

    def should_short(self):
        """
        A winning trade that is closed with the takeProfit order.
        notice that in this trade is very short-lived. In fact, it's
        opened and closed inside the very same 5m candle.
        Notice that this is even done via a STOP order
        thanks to Jesse's ability to trade on forming-candles.
        """
        return self.time == 1547203500000 + 60_000

    def go_long(self):
        qty = 10.204
        self.buy = qty, 129.33
        self.stop_loss = qty, 128.35
        self.take_profit = qty, 131.29

    def go_short(self):
        qty = 10
        self.sell = qty, 128.05
        self.stop_loss = qty, 129.52
        self.take_profit = qty, 126.58

    def should_cancel(self):
        return False

    def filters(self):
        return []
