from jesse.strategies import Strategy


# test_on_route_close_position part 2 - ETH-USD
class Test24(Strategy):
    def should_long(self):
        return self.price == 10

    def should_short(self):
        return False

    def go_long(self):
        self.buy = 1, self.price
        self.take_profit = 1, 20

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
