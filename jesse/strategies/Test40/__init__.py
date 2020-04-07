from jesse.strategies import Strategy


# test_open_pl_and_total_open_trades
class Test40(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test40', '0.0.1', exchange, symbol, timeframe)

    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, 2

    def go_short(self):
        pass

    def should_cancel(self):
        return False
