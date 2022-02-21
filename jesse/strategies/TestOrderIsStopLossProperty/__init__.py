from jesse.strategies import Strategy
import jesse.helpers as jh


class TestOrderIsStopLossProperty(Strategy):
    def should_long(self):
        return False

    def should_short(self):
        return self.index == 0

    def should_cancel(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        self.sell = 1, self.price
        self.stop_loss = 1, self.price + 5

    def on_close_position(self, order) -> None:
        assert order.is_stop_loss == True
