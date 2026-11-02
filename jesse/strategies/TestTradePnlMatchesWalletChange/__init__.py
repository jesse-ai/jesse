from jesse.strategies import Strategy


class TestTradePnlMatchesWalletChange(Strategy):
    """
    Opens three trades that each scale in and out. The first two are closed by the strategy
    and the last one is left open, so that it gets closed by the end of the backtest.
    """

    def should_long(self):
        return self.index in (5, 35, 65)

    def go_long(self):
        self.vars['wallet_before_entry'] = self.position.exchange.assets['USDT']
        self.vars['entry_index'] = self.index
        self.buy = 2, self.price

    def update_position(self):
        candles_since_entry = self.index - self.vars['entry_index']

        if candles_since_entry == 5:
            self.buy = 1, self.price
        elif candles_since_entry == 10:
            self.take_profit = self.position.qty / 3, self.price
        elif candles_since_entry == 20 and self.index != 85:
            self.liquidate()

    def on_close_position(self, order, closed_trade) -> None:
        wallet_change = self.position.exchange.assets['USDT'] - self.vars['wallet_before_entry']
        assert round(closed_trade.pnl, 8) == round(wallet_change, 8)

    def should_cancel_entry(self):
        return False
