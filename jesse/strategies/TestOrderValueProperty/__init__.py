from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestOrderValueProperty(Strategy):
    def before(self) -> None:
        if self.price == 11:
            # get entry order
            entry_order = self.entry_orders[0]
            assert entry_order.value == 16

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def should_short(self) -> bool:
        return self.price == 10

    def go_short(self) -> None:
        self.sell = 2, 8

    def should_cancel_entry(self):
        return False
