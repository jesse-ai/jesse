from jesse.strategies import Strategy


# test_has_entry_orders
class TestHasEntryOrders(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price + 2
        self.take_profit = qty, self.price + 4

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def before(self):
        if 0 < self.index < 2:
            assert self.has_active_entry_orders is True
