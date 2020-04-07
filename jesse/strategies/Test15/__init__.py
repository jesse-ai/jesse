from jesse.strategies import Strategy


# test_opening_position_in_multiple_points
class Test15(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test15', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        return self.price < 7

    def should_short(self):
        return False

    def go_long(self):
        self.buy = [
            (.5, 7),
            (.5, 9),
            (.5, 11),
        ]
        self.stop_loss = 1.5, 5
        self.take_profit = 1.5, 15

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []
