from jesse.strategies import Strategy


# test_on_route_canceled part 2 - ETH-USD
class Test28(Strategy):
    def should_long(self):
        return self.price == 10

    def should_short(self):
        return False

    def go_long(self):
        # because we know the price is going up, this order will never get filled
        self.buy = 1, self.price - 9

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return self.price == 20
