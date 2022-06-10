from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestBalancesAreHandledCorrectlyForCancellingOrdersInSpot(Strategy):
    def should_long(self):
        return self.price in [10, 40]

    def go_long(self):
        if self.price == 10:
            assert self.balance == 10_000
            # submit a LIMIT order that is not supposed to get executed
            self.buy = 2, self.price - 2
        if self.price == 40:
            # submit a MARKET order that is supposed to get executed immediately
            self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        if self.price == 40:
            assert self.balance == 10_000 - 40
            assert self.position.qty == 1

            # submit stop-loss order
            self.stop_loss = self.position.qty, 30
            # submit take-profit order
            self.take_profit = self.position.qty, 80

    def before(self) -> None:
        if self.price == 12:
            assert self.average_entry_price == 8

        elif self.price == 41:
            assert self.position.qty == 1
            assert self.average_take_profit == 80
            assert self.average_stop_loss == 30

    def on_close_position(self, order) -> None:
        assert order.is_take_profit is True
        assert self.price == 80
        assert self.position.qty == 0
        assert self.balance == 10_000 + 40

    def should_cancel_entry(self):
        return self.price == 12
