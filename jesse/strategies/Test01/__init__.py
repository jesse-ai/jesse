from jesse.strategies import Strategy


# test_should_buy_and_execute_buy
class Test01(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price
        self.stop_loss = qty, self.price - 10
        self.take_profit = qty, self.price + 10

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
