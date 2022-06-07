from jesse.strategies import Strategy


# test_increaed_and_reduced_count
class TestIncreasedAndReducedCount(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price

    def update_position(self):
        if self.position.qty == 1 and self.index == 1:
            assert self.reduced_count == 0

            assert self.increased_count == 1
            # now increase position
            self.buy = 1, self.price

        elif self.position.qty == 2:
            assert self.increased_count == 2

            # reduce it by one
            self.take_profit = 0.5, self.price
        elif self.position.qty == 1.5:
            assert self.reduced_count == 1
            self.take_profit = 0.5, self.price
        else:
            assert self.reduced_count == 2

            # close trade
            self.liquidate()

    def before(self):
        if self.trades_count == 1:
            assert self.increased_count == 0
            assert self.reduced_count == 0

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
