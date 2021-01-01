from jesse.strategies import Strategy


# test_on_route_increased_position_and_on_route_reduced_position_and_strategy_vars part 2 - ETH-USD
class Test30(Strategy):
    def update_position(self):
        # increase position size
        if self.price == 20:
            self.buy = 1, self.price

        # decrease position size
        if self.price == 50:
            self.take_profit = 1, self.price

        # close position with take_profit
        if self.price == 70:
            self.take_profit = self.position.qty, self.price

    def should_long(self):
        return self.price == 10

    def should_short(self):
        return False

    def go_long(self):
        self.buy = 1, self.price

    def go_short(self):
        pass

    def should_cancel(self):
        return False
