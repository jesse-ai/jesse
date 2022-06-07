from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCanSubmitTakeProfitOrderWithSizeLessThanCurrentPositionQty(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = [
            (0.5, 15),
            (0.5, 20),
        ]

    def on_increased_position(self, order) -> None:
        assert order.qty == 0.5
        assert order.price == 15
        assert order.is_take_profit is True

    def on_close_position(self, order) -> None:
        assert abs(order.qty) == 0.5
        assert order.price == 20
        assert order.is_take_profit is True

    def should_cancel_entry(self):
        return False
