from jesse.strategies import Strategy


# test_filter_readable_exception
class Test47(Strategy):
    def should_long(self) -> bool:
        return True

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price
        self.stop_loss = qty, self.price - .10

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return [
            self.filter_1()
        ]

    def filter_1(self):
        if self.index == 0:
            return False

        if self.index == 10:
            return False

        return True
