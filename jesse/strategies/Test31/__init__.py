from jesse.strategies import Strategy


# test_liquidate
class Test31(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test31', '0.0.1', exchange, symbol, timeframe)

    def update_position(self):
        # for long trade (first)
        if self.index == 10:
            self.liquidate()

        # for short trade (second)
        if self.index == 40:
            self.liquidate()

    def should_long(self):
        return self.index == 0

    def should_short(self):
        return self.index == 20

    def go_long(self):
        self.buy = 1, self.price

    def go_short(self):
        self.sell = 1, self.price

    def should_cancel(self):
        return False
