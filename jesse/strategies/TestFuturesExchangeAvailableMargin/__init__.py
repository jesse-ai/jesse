from jesse import utils
from jesse.strategies import Strategy


class TestFuturesExchangeAvailableMargin(Strategy):
    def before(self):
        if self.index == 0:
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            assert self.position.exchange.available_margin == 20000 == self.available_margin

        if self.price == 11:
            # wallet balance should have stayed the same while we haven't spent from it yet
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            # but available_margin should have
            assert round(self.position.exchange.available_margin) == 20000 - 2000 == round(self.available_margin)

        if self.price == 12:
            # wallet balance should have changed because of fees, but we have fee=0 in this test, so:
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            # position is opened at this price, but the available_margin should have stayed the same (and NOT
            # include the take_profit and stop_loss which are reduce only orders
            assert round(self.position.exchange.available_margin) == 20000 - 2000 + self.position.pnl == round(self.available_margin)

        if self.price == 13:
            # wallet balance should have changed because of fees, but we have fee=0 in this test, so:
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            # position is opened at this price, but the available_margin should have stayed the same (and NOT
            # include the take_profit and stop_loss which are reduce only orders. NOTICE that the unrealized
            # profit of the open position multiplied by the leverage should also have been added
            assert round(self.available_margin) == round(20000 - 2000 + self.position.pnl * self.leverage)

        if self.price == 21:
            # wallet balance must now equal to 10_000 + the profit we made from previous trade
            previous_trade = self.trades[0]
            assert self.position.exchange.wallet_balance == previous_trade.pnl + 10000
            # now that position is closed, available_margin should equal to wallet_balance*leverage
            assert self.available_margin == self.position.exchange.wallet_balance * 2
            assert self.balance == self.position.exchange.wallet_balance
            assert self.balance * self.leverage == self.available_margin

    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = utils.size_to_qty(2000, 12)
        self.buy = qty, 12
        self.take_profit = qty, 20
        self.stop_loss = qty, 10

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
