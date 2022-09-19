from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestBeforeTerminate(Strategy):
    def __init__(self):
        super().__init__()
        self.__before_terminate_called = False

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price

    def should_cancel_entry(self):
        return False

    def before_terminate(self):
        self.__before_terminate_called = True

    def terminate(self):
        assert self.__before_terminate_called is True
