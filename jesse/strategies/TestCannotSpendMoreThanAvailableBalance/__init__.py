from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCannotSpendMoreThanAvailableBalance(Strategy):
    def should_long(self):
        return self.index == 0

    def go_long(self):
        # try to spend 110% of available balance
        qty = utils.size_to_qty(self.balance*1.1, self.price)
        self.buy = qty, self.price

    def should_cancel_entry(self):
        return False
