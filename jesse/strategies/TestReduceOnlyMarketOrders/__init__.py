from jesse import utils
from jesse.strategies import Strategy


class TestReduceOnlyMarketOrders(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        entry = self.price
        qty = utils.size_to_qty(self.capital, entry, fee_rate=self.fee_rate)
        self.buy = qty, entry

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def update_position(self):
        if self.price == 20:
            self.liquidate()
