from jesse.strategies import Strategy


# test_open_pl_and_total_open_trades
class Test40(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, 2

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
