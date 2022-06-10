from jesse.strategies import Strategy
import jesse.helpers as jh


class CanAddClosedTradeToStore(Strategy):
    def should_long(self):
        return self.price == 10

    def should_cancel_entry(self):
        return False

    def go_long(self):
        self.buy = 1, self.price
        self.take_profit = 1, 15
