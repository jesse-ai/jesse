from jesse.strategies import Strategy


# test_taking_profit_at_multiple_points
class Test10(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test10', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        return self.price < 7

    def should_short(self):
        return False

    def go_long(self):
        qty = 1.5
        self.buy = qty, 7
        self.stop_loss = qty, 5
        self.take_profit = [
            (0.5, 11),
            (0.5, 13),
            (0.5, 15)
        ]

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []
