from jesse.strategies import Strategy


# test_on_reduced_position
class Test18(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test18', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        return self.price < 7

    def go_long(self):
        qty = 2

        self.buy = qty, 7
        self.stop_loss = qty, 5
        self.take_profit = [
            (1, 15),
            (1, 13)
        ]

    def on_reduced_position(self):
        self.take_profit = abs(self.position.qty), self.price

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []

    def should_short(self):
        return False
