from jesse.strategies import Strategy


# test_should_sell_and_execute_sell
class Test02(Strategy):
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

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
