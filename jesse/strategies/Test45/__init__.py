from jesse.strategies import Strategy


# test_can_close_a_long_position_and_go_short_at_the_same_candle
class Test45(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return self.index != 0

    def go_long(self):
        qty = 1
        self.buy = qty, self.price

    def go_short(self):
        qty = 1
        self.sell = qty, self.price
        assert self.index == 1

    def should_cancel(self):
        return False

    def update_position(self):
        if self.index == 1:
            self.liquidate()
