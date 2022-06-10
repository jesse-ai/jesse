from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCanSubmitTakeProfitOrderWithSizeEqualToCurrentPositionQty(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = self.position.qty, 15

    def on_close_position(self, order) -> None:
        assert order.is_take_profit is True
        assert order.price == 15

    def should_cancel_entry(self):
        return False
