from jesse.strategies import Strategy


class TestMarketOrderForLowPriceDifference(Strategy):
    def on_open_position(self, order):
        assert order.type == 'MARKET'

    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        # current-price: 1
        self.buy = 1, 1.00001

    def go_short(self):
        pass

    def should_cancel(self):
        return False
