from jesse.strategies import Strategy


# test_shared_vars [part 2]
class Test33(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test33', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        return self.trades_count == 0 and self.shared_vars['buy-eth'] is True

    def should_short(self):
        return False

    def go_long(self):
        self.buy = 1, self.price
        self.take_profit = 1, self.price + 10

    def go_short(self):
        pass

    def should_cancel(self):
        return False
