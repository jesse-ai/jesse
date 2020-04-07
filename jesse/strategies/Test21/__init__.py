from jesse.strategies import Strategy


# test_on_route_open_position part 1 - BTCUSD
class Test21(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test21', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        # buy on market at first candle, close when on_route_open_position event is fired
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

    def on_route_open_position(self, strategy):
        self.take_profit = 1, self.price
