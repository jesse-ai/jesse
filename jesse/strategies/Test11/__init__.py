from jesse.strategies import Strategy


# test_stop_loss_at_multiple_points
class Test11(Strategy):
    def should_long(self):
        return False

    def should_short(self):
        return self.index == 0

    def go_long(self):
        pass

    def go_short(self):
        qty = 1.5
        self.sell = qty, 3
        self.stop_loss = [
            (0.5, 6),
            (0.5, 5),
            (0.5, 4)
        ]
        self.take_profit = qty, 1

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
