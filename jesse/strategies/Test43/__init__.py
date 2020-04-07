from jesse.strategies import Strategy
from jesse.services import logger


# test_is_reduced
class Test43(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test43', '0.0.1', exchange, symbol, timeframe)

    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        self.buy = 1, 2
        self.take_profit = [
            (.5, 6),
            (.5, 10),
        ]

    def update_position(self):
        if self.position.qty == 1:
            assert not self.is_increased
            assert not self.is_reduced
        elif self.position.qty == .5:
            assert not self.is_increased
            assert self.is_reduced

    def go_short(self):
        pass

    def should_cancel(self):
        return False
