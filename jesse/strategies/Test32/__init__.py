from jesse.strategies import Strategy


# test_shared_vars [part 1]
class Test32(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test32', '0.0.1', exchange, symbol, timeframe)

        self.shared_vars['buy-eth'] = False

    def prepare(self):
        if self.index == 10:
            self.shared_vars['buy-eth'] = True

    def should_long(self):
        return False

    def should_short(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel(self):
        return False
