from jesse import utils
from jesse.strategies import Strategy


# test_negative_balance_validation_for_futures_market
class TestInsufficientMargin3(Strategy):
    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return self.index == 0

    def go_long(self):
        pass

    def go_short(self):
        qty = utils.size_to_qty(10_001, self.price * .99)
        self.sell = qty, self.price * .99

    def should_cancel_entry(self):
        return False
