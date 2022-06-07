from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCanSubmitStopLossOrderWithSizeLessThanCurrentPositionQty(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.stop_loss = [
            (0.5, 8),
            (0.5, 5),
        ]

    def on_reduced_position(self, order) -> None:
        assert order.is_stop_loss is True
        assert order.qty == 0.5
        assert order.price == 8

    def on_close_position(self, order) -> None:
        assert order.is_stop_loss is True
        assert order.price == 5

    def should_cancel_entry(self):
        return False
