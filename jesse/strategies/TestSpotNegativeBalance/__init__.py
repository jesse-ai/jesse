from jesse.strategies import Strategy
from jesse import utils


# test_negative_balance_validation_for_spot_market
class TestSpotNegativeBalance(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = utils.size_to_qty(10_001, self.price)
        self.buy = qty, self.price

    def go_short(self):
        pass

    def should_cancel(self):
        return False
