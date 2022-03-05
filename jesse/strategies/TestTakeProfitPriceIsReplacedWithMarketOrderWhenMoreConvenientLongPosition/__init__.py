from jesse.strategies import Strategy
from jesse.enums import order_types


class TestTakeProfitPriceIsReplacedWithMarketOrderWhenMoreConvenientLongPosition(Strategy):
    def before(self) -> None:
        if self.price == 15:
            last_trade = self.trades[-1]
            # it should have closed on the market price at the time being 10 instead of 8
            assert last_trade.exit_price == 10

            # the order type should be market
            assert self.trades[-1].orders[0].type == order_types.MARKET
            assert self.trades[-1].orders[1].type == order_types.MARKET

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self):
        self.buy = 1, 10
        self.take_profit = 1, 8

    def should_short(self) -> bool:
        return False

    def go_short(self):
        pass

    def should_cancel(self):
        return False
