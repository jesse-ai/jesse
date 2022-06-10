from jesse.strategies import Strategy


# test_conflicting_orders
class Test04(Strategy):
    def should_long(self):
        return self.index == 0

    def should_short(self):
        return False

    def go_long(self):
        # print(self.open, self.close, self.high, self.low)
        # 0.5, 1.0, 1.0, 0.5

        qty = 2
        # current_price: 1
        # entry: 1.1
        entry = 1.1
        # stop_loss: 1.0
        # take_profit: 1.2
        self.buy = [
            (1, round(entry, 2)),
            (1, round(entry + 0.01, 2)),
            # (1, round(entry + 0.015, 2))
        ]
        # this one should not get executed at all
        self.stop_loss = qty, entry - 0.1
        self.take_profit = [
            (1, round(entry + 0.1, 2)),
            (1, round(entry + 0.2, 2))
        ]

        # the candle when the open_position order gets hit:
        # 1, 2, 2, 1

        # what SHOULD happen in the next candle:
        # the current price should be 1.1 instead of 2. hence a candle open-close = 1-1.1
        # loop:
        # then we create a temp candle open-close = 1.1-(next_order_price else 2)
        # next (increasing) order will get executed next, then take_profit
        # when this is all over, we then add(update) the candle we had in the first place which is 1, 2, 2, 1

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
