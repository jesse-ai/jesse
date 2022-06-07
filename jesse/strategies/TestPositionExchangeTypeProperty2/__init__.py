from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestPositionExchangeTypeProperty2(Strategy):
    def before(self) -> None:
        if self.index == 0:
            assert self.exchange_type == 'spot'

    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_cancel_entry(self):
        return False
