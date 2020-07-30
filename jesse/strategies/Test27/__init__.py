from jesse.strategies import Strategy


# test_on_route_canceled part 1 - BTCUSD
class Test27(Strategy):
    def should_long(self):
        # buy on market at first candle, close when on_route_stop_loss event is fired
        return self.index == 0

    def should_short(self):
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def on_route_canceled(self, strategy):
        """

        :param strategy:
        """
        self.take_profit = 1, self.price
