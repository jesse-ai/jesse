from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestOnCancelMethod(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        if self.price == 10:
            # submit a LIMIT order that is not supposed to get executed
            self.buy = 1, self.price - 2

    def should_cancel_entry(self):
        return self.price == 12

    def on_cancel(self) -> None:
        assert self.price == 12
