from jesse.strategies import Strategy


# test_on_route_close_position part 1 - BTC-USD
class Test23(Strategy):
    def should_long(self):
        # buy on market at first candle, close when on_route_take_profit event is fired
        return self.index == 0

    def should_short(self):
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def on_route_close_position(self, strategy) -> None:
        self.take_profit = 1, self.price
