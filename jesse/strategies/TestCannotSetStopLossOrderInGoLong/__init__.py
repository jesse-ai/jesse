from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCannotSetStopLossOrderInGoLong(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price
        self.stop_loss = 1, self.price - 1

    def should_cancel_entry(self):
        return False
