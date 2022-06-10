from jesse.strategies import Strategy


# test_filters
class Test37(Strategy):
    def before(self):
        """used it to do assertions"""
        if self.index in [3, 11]:
            assert self.take_profit is None
            assert self.stop_loss is None

    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return self.index == 10

    def go_long(self):
        qty = 1
        self.buy = qty, self.price
        self.stop_loss = qty, self.price - .10

    def go_short(self):
        qty = 1
        self.sell = qty, self.price
        self.take_profit = qty, self.price + .10

    def should_cancel_entry(self):
        return False

    def filters(self):
        return [
            self.filter_1
        ]

    def filter_1(self):
        if self.index == 0:
            return False

        if self.index == 10:
            return False

        return True
