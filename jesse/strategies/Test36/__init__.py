from jesse.strategies import Strategy


# test_average_take_profit_and_average_stop_loss
class Test36(Strategy):
    def should_long(self):
        # filter_1 will pass 0, but not 8
        return self.index in [0, 8]

    def should_short(self):
        return self.index == 10

    def go_long(self):
        entry = self.price
        self.buy = 2, entry
        self.take_profit = [
            (1, 3),
            (1, 4),
        ]

    def go_short(self):
        entry = self.price
        self.sell = 2, entry
        self.stop_loss = [
            (1, 13),
            (1, 14),
        ]

    def should_cancel_entry(self):
        return True

    def filters(self):
        return [
            self.filter_1
        ]

    def filter_1(self):
        if self.index == 0 and self.average_take_profit == 3.5:
            return True

        if self.index == 10 and self.average_stop_loss == 13.5:
            return True

        return False
