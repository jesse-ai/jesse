from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils


class ExampleStrategy(Strategy):
    def __init__(self, exchange, symbol, timeframe, hyper_parameters=None):
        super().__init__('ExampleStrategy', '0.0.1', exchange, symbol, timeframe)

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def should_cancel(self) -> bool:
        return True

    def go_long(self):
        pass

    def go_short(self):
        pass
