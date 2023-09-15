from jesse.strategies import Strategy

class TestMarketOrderForLowPriceDifference(Strategy):
    def on_open_position(self, order):
        assert order.type == 'MARKET'

    def on_close_position(self, order) -> None:
        assert order.type == 'MARKET'

    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        # current-price: 1
        self.buy = 1, 1.0001

    def update_position(self) -> None:
        # submit a take-profit order that has a low difference with the current price
        self.take_profit = self.position.qty, self.price + 0.0001

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
