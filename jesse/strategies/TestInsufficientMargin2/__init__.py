from jesse import utils
from jesse.strategies import Strategy


# test_negative_balance_validation_for_futures_market
class TestInsufficientMargin2(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = utils.size_to_qty(10_001, self.price * .99)
        self.buy = qty, self.price * .99

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
