from jesse.strategies import Strategy
from jesse import utils
import jesse.helpers as jh
from jesse.services import selectors


class TestProperBalanceHanldingInSpotAfterOrderCancellation(Strategy):
    def before(self) -> None:
        # after the first trade
        if self.price == 89:
            assert self.balance == 9900
            e = selectors.get_exchange(self.exchange)
            assert e.assets['USDT'] == 9900
            assert e.assets['BTC'] == 0
        
    def should_long(self):
        return self.price == 100

    def go_long(self):
        entry = self.price
        qty = utils.size_to_qty(1000, entry)
        self.buy = qty, entry

    def on_open_position(self, order):
        self.take_profit = self.position.qty, 110
        self.stop_loss = self.position.qty, 90
    