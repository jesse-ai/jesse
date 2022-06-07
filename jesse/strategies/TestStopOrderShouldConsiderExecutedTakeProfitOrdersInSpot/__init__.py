from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestStopOrderShouldConsiderExecutedTakeProfitOrdersInSpot(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = 2, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = [
            (1, 15),
            (1, 20),
        ]

    def on_reduced_position(self, order) -> None:
        assert self.position.qty == 1
        self.stop_loss = 1, self.price - 1

    def on_close_position(self, order) -> None:
        last_trade = self.trades[-1]

        if self.trades_count == 1:
            assert last_trade.exit_price == 17.5
            assert last_trade.entry_price == 10
            assert last_trade.qty == 2
            assert last_trade.type == "long"

    def should_cancel_entry(self):
        return False
