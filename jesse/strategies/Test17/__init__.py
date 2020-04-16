from jesse.strategies import Strategy


# test_reducing_position_size_after_opening
class Test17(Strategy):
    def should_long(self):
        return self.price < 7

    def go_long(self):
        qty = 2

        self.buy = qty, 7
        self.stop_loss = qty, 5
        self.take_profit = qty, 15

    def update_position(self):
        # reduce the size of position for 1 at current price
        if self.price == 10:
            # should work even without resetting take_profit and stop_loss
            self.take_profit = [
                (1, self.price),
                (1, 15)
            ]

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []

    def should_short(self):
        return False
