from jesse.strategies import Strategy


# test_on_route_stop_loss part 2 - ETHUSD
class Test26(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test26', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        return False

    def should_short(self):
        return self.price == 10

    def go_long(self):
        pass

    def go_short(self):
        self.sell = 1, self.price
        self.stop_loss = 1, 20

    def should_cancel(self):
        return False
