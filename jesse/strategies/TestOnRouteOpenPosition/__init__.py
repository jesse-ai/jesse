from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestOnRouteOpenPosition(Strategy):
    def before(self) -> None:
        if self.index == 0:
            assert self.symbol == 'BTC-USDT'

        if self.price == 20:
            assert self.is_open

        if self.price == 21:
            assert self.is_close

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price

    def should_cancel_entry(self):
        return False

    def on_route_open_position(self, strategy) -> None:
        if self.is_open and strategy.symbol == 'ETH-USDT':
            self.liquidate()
