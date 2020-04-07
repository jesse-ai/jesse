from jesse.strategies import Strategy


# test_average_take_profit_exception
class Test38(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test38', '0.0.1', exchange, symbol, timeframe)

    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, 2
        self.stop_loss = qty, 1

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return [self.filter_1]

    def filter_1(self):
        # trying to access average_take_profit without setting it first
        return self.average_take_profit > 1
