from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCanSubmitTakeProfitAndStopLossAtSameTimeInSpot(Strategy):
    def should_long(self):
        return self.price in [10, 20]

    def go_long(self):
        if self.price == 10:
            self.buy = 1, self.price
        elif self.price == 20:
            self.buy = 2, self.price

    def on_open_position(self, order) -> None:
        if self.price == 10:
            self.take_profit = self.position.qty, 15
            self.stop_loss = self.position.qty, 8
        elif self.price == 20:
            self.take_profit = self.position.qty, 30
            self.stop_loss = self.position.qty, 15

    def on_close_position(self, order) -> None:
        last_trade = self.trades[-1]

        if self.trades_count == 1:
            assert last_trade.exit_price == 15
            assert last_trade.entry_price == 10
            assert last_trade.qty == 1
            assert last_trade.type == "long"
        elif self.trades_count == 2:
            assert last_trade.exit_price == 30
            assert last_trade.entry_price == 20
            assert last_trade.qty == 2

    def should_cancel_entry(self):
        return False
