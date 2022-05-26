from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestFeeReductionWorksCorrectlyInSpotModeInBothBuyAndSellOrders(Strategy):
    def before(self) -> None:
        if self.index == 0:
            assert self.capital == 10_000
            assert self.position.exchange.assets['BTC'] == self.position.qty == 0

    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = [
            (1, 10),
            (2, 12)
        ]

    def on_open_position(self, order) -> None:
        assert order.qty == 1
        assert self.position.qty == 0.999 == self.position.exchange.assets['BTC']
        assert self.capital == 9966
        self.vars['called_on_open_position'] = True

    def on_increased_position(self, order) -> None:
        assert order.qty == 2
        assert self.position.qty == 2.997 == self.position.exchange.assets['BTC']
        assert self.capital == 9966
        self.vars['called_on_increased_position'] = True

        # submit reduce and closing orders
        self.take_profit = [
            (0.999, 15),
            (1.998, 17),
        ]

    def on_reduced_position(self, order) -> None:
        assert order.qty == -0.999
        assert self.position.qty == 1.998 == self.position.exchange.assets['BTC']
        assert self.capital == 9966 + 14.970015
        self.vars['called_on_reduced_position'] = True

    def on_close_position(self, order) -> None:
        assert order.qty == -1.998
        assert self.capital == 9966 + 14.970015 + 33.932034
        self.vars['called_on_close_position'] = True

        # just in case assert the amounts in the exchange
        assert self.position.exchange.assets['USDT'] == self.capital
        assert self.position.exchange.assets['BTC'] == self.position.qty == 0

    def should_cancel(self):
        return False
