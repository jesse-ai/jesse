from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestOrderPriceCannotBeGreaterThanZero(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, 0

    def should_cancel_entry(self):
        return False
