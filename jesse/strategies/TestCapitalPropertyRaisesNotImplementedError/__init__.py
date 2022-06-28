from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestCapitalPropertyRaisesNotImplementedError(Strategy):
    def should_long(self) -> bool:
        self.capital
        return False

    def go_long(self) -> None:
        pass

    def should_cancel_entry(self):
        return False
