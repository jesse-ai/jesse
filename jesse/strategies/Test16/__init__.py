from jesse.strategies import Strategy


# test_increasing_position_size_after_opening
class Test16(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test16', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        return self.price < 7

    def go_long(self):
        qty = 1

        self.buy = qty, 7
        self.stop_loss = qty, 5
        self.take_profit = qty, 15

    def update_position(self):
        # buy 1 more at current price
        if self.price == 10:
            self.buy = 1, 10
            self.take_profit = 2, 15
            self.stop_loss = 2, 5

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []

    def should_short(self):
        return False
