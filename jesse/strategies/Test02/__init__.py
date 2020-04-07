from jesse.strategies import Strategy


# test_should_sell_and_execute_sell
class Test02(Strategy):
    def __init__(self, exchange, symbol, timeframe):
        super().__init__('Test02', '0.0.1', exchange, symbol, timeframe)

    def should_long(self):
        return False

    def should_short(self):
        # sell on market at first candle, and sell on the third candle
        return len(self.candles) == 1

    def go_long(self):
        pass

    def go_short(self):
        qty = 1
        self.sell = qty, self.price
        self.stop_loss = qty, self.price + 10
        self.take_profit = qty, self.price - 10

    def should_cancel(self):
        return False

    def filters(self):
        return []
