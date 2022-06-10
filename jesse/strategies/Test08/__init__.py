from jesse.strategies import Strategy


# test_stats_for_a_strategy_without_losing_trades
class Test08(Strategy):
    def should_long(self):
        return False

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
        qty = 10.2041

        self.buy = qty, 129.33
        self.stop_loss = 128.35
        self.take_profit = 131.29

    def go_short(self):
        qty = 10

        self.sell = qty, 128.05
        self.stop_loss = qty, 129.52
        self.take_profit = qty, 126.58

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
