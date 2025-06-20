from jesse.strategies import Strategy


class TestMetrics2(Strategy):
    def should_long(self) -> bool:
        return self.price < 15

    def should_short(self) -> bool:
        return self.price > 15

    def go_long(self):
        self.buy = 10, 10

    def go_short(self):
        self.sell = 10, 20

    def should_cancel_entry(self):
        return True

    def on_open_position(self, order):
        # sell it for $50 profit
        self.take_profit = self.position.qty, 15
