from jesse.strategies import Strategy


# test_validation_for_equal_stop_loss_and_take_profit
class Test46(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        self.buy = 1, 2

    def update_position(self):
        if self.index == 5:
            self.stop_loss = 1, 3
            self.take_profit = 1, 3

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
