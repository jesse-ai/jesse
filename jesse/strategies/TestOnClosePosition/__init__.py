from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestOnClosePosition(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        if self.price == 10:
            self.buy = 1, self.price
    
    def on_open_position(self, order):
        self.take_profit = 1, 12 # close the position at 12

    def on_close_position(self, order, closed_trade) -> None:
        assert closed_trade.exit_price == 12
        assert closed_trade.entry_price == 10
        assert closed_trade.qty == 1
        assert closed_trade.type == "long"
        assert closed_trade.timeframe == self.timeframe
        assert closed_trade.exchange == self.exchange
        assert closed_trade.symbol == self.symbol
