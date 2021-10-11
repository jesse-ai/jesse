from jesse.strategies import Strategy


# test_on_route_close_position part 2 - ETH-USD
class Test26(Strategy):
    def should_long(self):
        return False

    def should_short(self):
        return self.price == 10

    def go_long(self):
        pass

    def go_short(self):
        self.sell = 1, self.price
        self.stop_loss = 1, 20

    def should_cancel(self):
        return False
