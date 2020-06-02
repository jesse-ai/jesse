from jesse.strategies import Strategy


class Test19(Strategy):
    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def go_long(self):
        # qty = 1
        # self.buy = qty, self.price
        # self.take_profit = qty, self.price + .1
        # self.stop_loss = qty, self.price - .1
        pass

    def go_short(self):
        # qty = 1
        # self.buy = qty, self.price
        # self.take_profit = qty, self.price + .1
        # self.stop_loss = qty, self.price - .1
        pass

    def should_cancel(self) -> bool:
        return False
