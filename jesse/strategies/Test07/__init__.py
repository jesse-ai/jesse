from jesse.strategies import Strategy


# test_updating_stop_loss_and_take_profit_after_opening_the_position
class Test07(Strategy):
    def should_long(self):
        return self.time == 1547201100000 + 60_000

    def go_long(self):
        qty = 10.204

        self.buy = qty, self.price
        self.stop_loss = qty, 128.35
        self.take_profit = qty, 131.29

    def should_short(self):
        return self.time == 1547203560000 + 60_000

    def go_short(self):
        qty = 10

        self.sell = qty, self.price
        self.stop_loss = qty, 129.52
        self.take_profit = qty, 126.58

    def should_cancel(self):
        return False

    def filters(self):
        return []

    def update_position(self):
        # early take-profit for short trade
        if self.time == 1547203680000 + 60_000:
            self.take_profit = self.position.qty, 127.66

        # early stop-loss for long trade
        if self.time == 1547201700000 + 60_000:
            self.stop_loss = self.position.qty, 128.98
