from jesse.strategies import Strategy
import jesse.indicators as ta


class Test19(Strategy):
    def __init__(self, exchange, symbol, timeframe, hyper_parameters=None):
        super().__init__('Test19', '0.0.1', exchange, symbol, timeframe)

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def go_long(self):
        # qty = 1
        # self.buy = qty, self.price
        # self.take_profit = qty, self.price + .1
        # self.stop_loss = qty, self.price - .1
        pass

    def go_short(self):
        # qty = 1
        # self.buy = qty, self.price
        # self.take_profit = qty, self.price + .1
        # self.stop_loss = qty, self.price - .1
        pass

    def should_cancel(self) -> bool:
        return False
