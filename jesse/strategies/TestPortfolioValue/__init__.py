from jesse.strategies import Strategy
from jesse import utils


class TestPortfolioValue(Strategy):
    def before(self):
        if self.index == 0:
            # starting capital
            assert self.portfolio_value == 10_000

        if self.index == 10:
            assert round(self.portfolio_value) == round((self.balance + self.all_positions['ETH-USDT'].pnl + self.all_positions['BTC-USDT'].pnl) * self.leverage)

    def should_long(self) -> bool:
        return self.index == 0 and self.symbol == 'ETH-USDT'

    def should_short(self) -> bool:
        return self.index == 0 and self.symbol == 'BTC-USDT'

    def go_long(self):
        qty = utils.size_to_qty(100, self.price)
        self.buy = qty, self.price

    def go_short(self):
        qty = utils.size_to_qty(10, self.price)
        self.sell = qty, self.price

    def should_cancel_entry(self):
        return False
