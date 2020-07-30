from jesse.strategies import Strategy


# test_multiple_routes_can_communicate_with_each_other
class Test03(Strategy):
    def should_long(self):
        return False

    def should_short(self):
        return len(self.candles) == 1

    def go_long(self):
        pass

    def go_short(self):
        qty = 1
        sell_price = self.price + 5

        self.sell = qty, sell_price
        self.stop_loss = qty, sell_price + 10
        self.take_profit = qty, sell_price - 10

    def should_cancel(self):
        return False

    def on_route_open_position(self, strategy):
        """

        :param strategy:
        """
        self._execute_cancel()

    def filters(self):
        return []
