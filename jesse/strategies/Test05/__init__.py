from jesse.strategies import Strategy
import jesse.helpers as jh


# test_is_smart_enough_to_open_positions_via_market_orders
class Test05(Strategy):
    def update(self):
        pass

    def should_long(self):
        return self.time == 1547201100000 + 60_000

    def should_short(self):
        return self.time == 1547203560000 + 60_000

    def go_long(self):
        qty = 10.204
        self.buy = qty, self.price
        self.stop_loss = qty, 128.35
        self.take_profit = qty, 131.29

    def go_short(self):
        qty = 10
        self.sell = qty, self.price
        self.stop_loss = qty, 129.52
        self.take_profit = qty, 126.58

    def should_cancel_entry(self):
        return False
