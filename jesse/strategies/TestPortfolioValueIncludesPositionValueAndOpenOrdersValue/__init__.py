from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestPortfolioValueIncludesPositionValueAndOpenOrdersValue(Strategy):
    def before(self) -> None:
        if self.price == 20:
            # portfolio value should be the current balance, plus the value
            # or the open order plus the value of the current open position
            assert self.portfolio_value == (10_000 - 10 - 8) + 8 + 20

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = [
            # executed order
            (1, 10),
            # left open order
            (1, 8),
        ]

    def should_cancel_entry(self):
        return False
