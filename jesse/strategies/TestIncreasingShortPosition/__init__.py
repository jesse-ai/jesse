from jesse.strategies import Strategy


class TestIncreasingShortPosition(Strategy):
    def before(self) -> None:
        # make sure The trade is closed
        if self.price == 70:
            last_trade = self.trades[-1]
            assert last_trade.qty == 2
            assert last_trade.entry_price == (90 + 88) / 2
            assert last_trade.exit_price == 80
            assert last_trade.type == 'short'
            assert self.trades_count == 1

    def should_short(self):
        return self.price == 90

    def go_short(self):
        self.sell = 1, 90

    def update_position(self):
        # buy 1 more at current price
        if self.price == 88:
            self.sell = 1, 88
            self.take_profit = 2, 80

    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
