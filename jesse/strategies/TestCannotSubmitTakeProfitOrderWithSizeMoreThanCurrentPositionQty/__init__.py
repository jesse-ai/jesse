from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCannotSubmitTakeProfitOrderWithSizeMoreThanCurrentPositionQty(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = self.position.qty*1.01, self.price*1.01

    def should_cancel_entry(self):
        return False
