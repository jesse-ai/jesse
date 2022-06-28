from jesse.strategies import Strategy


# test_can_handle_multiple_entry_orders_too_close_to_each_other
class Test34(Strategy):
    def should_long(self):
        return self.index == 0

    def should_short(self):
        return False

    def go_long(self):
        entry = 1
        self.buy = [
            (1, entry + 0.1),
            (1, entry + 0.2),
            (1, entry + 0.3),
            (1, entry + 0.4),
        ]
        self.stop_loss = 4, 0.4
        self.take_profit = 4, 3

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
