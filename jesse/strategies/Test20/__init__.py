from jesse.strategies import Strategy


# test_conflicting_orders_2
class Test20(Strategy):
    def should_long(self):
        return self.index == 1

    def should_short(self):
        return False

    def go_long(self):
        # self.price = 2
        qty = 1

        self.buy = qty, self.price + .5
        self.stop_loss = qty, self.price + .4
        self.take_profit = qty, self.price + .6

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def filters(self):
        return []
