from jesse.strategies import Strategy


# test_should_buy_and_execute_buy
class Test01(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test01', '0.0.1', exchange, symbol, timeframe)

    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price
        self.stop_loss = qty, self.price - 10
        self.take_profit = qty, self.price + 10

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []
