from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestPositionTotalCostProperty(Strategy):
    def before(self) -> None:
        if self.price == 20:
            if self.exchange_type == 'futures':
                assert self.position.entry_price * self.position.qty == 100
                assert self.leverage == 2
                assert self.position.total_cost == 50
            elif self.exchange_type == 'spot':
                assert self.position.entry_price * self.position.qty == 100
                assert self.leverage == 1
                assert self.position.total_cost == 100

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 10, self.price

    def should_cancel_entry(self):
        return False
