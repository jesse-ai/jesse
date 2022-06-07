from jesse.strategies import Strategy
import jesse.helpers as jh


class TestOrderIsTakeProfitProperty(Strategy):
    def should_long(self):
        return self.index == 0

    def should_cancel_entry(self):
        return False

    def go_long(self):
        self.buy = 1, self.price
        self.take_profit = 1, self.price + 5

    def on_close_position(self, order) -> None:
        assert order.is_take_profit == True
