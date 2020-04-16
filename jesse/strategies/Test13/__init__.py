from jesse.strategies import Strategy


# test_modifying_take_profit_after_part_of_position_is_already_reduced_with_profit
class Test13(Strategy):
    def should_long(self):
        return self.price < 7

    def should_short(self):
        return False

    def go_long(self):
        qty = 1.5
        self.buy = qty, 7
        self.stop_loss = qty, 5
        self.take_profit = [
            (0.5, 11),
            (0.5, 13),
            (0.5, 15)
        ]

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []

    def update_position(self):
        if self.is_reduced:
            self.take_profit = self.position.qty, 16
