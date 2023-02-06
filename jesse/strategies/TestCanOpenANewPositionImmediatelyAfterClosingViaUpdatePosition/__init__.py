from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCanOpenANewPositionImmediatelyAfterClosingViaUpdatePosition(Strategy):
    def before(self) -> None:
        if self.price == 21:
            assert self.position.entry_price == 20

    def should_long(self) -> bool:
        return self.price in [10, 20]

    def go_long(self) -> None:
        self.buy = 1, self.price

    def update_position(self) -> None:
        if self.price == 20:
            self.liquidate()

    def should_cancel_entry(self):
        return False
