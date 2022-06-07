from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestUsageOfShouldCancelRaisesNotImplementedError(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price - 5

    def should_cancel(self) -> bool:
        return False
