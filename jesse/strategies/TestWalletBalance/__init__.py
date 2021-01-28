from jesse.strategies import Strategy
from jesse import utils


# test_wallet_balance_for_futures_market
class TestWalletBalance(Strategy):
    def before(self):
        if self.index == 0:
            assert self.position.exchange.wallet_balance() == 10000 == self.capital == self.balance
            assert self.position.exchange.available_margin() == 20000 == self.available_margin

        if self.price == 11:
            # wallet balance should have stayed the same while we haven't spent from it yet
            assert self.position.exchange.wallet_balance() == 10000 == self.balance
            # but available_margin should have
            assert round(self.position.exchange.available_margin()) == 20000 - 4000 == round(self.available_margin)

        if self.price == 12:
            # wallet balance should have changed because of fees, but we have fee=0 in this test, so:
            assert self.position.exchange.wallet_balance() == 10000 == self.balance
            assert round(self.position.exchange.available_margin()) == 20000 - 4000 == round(self.available_margin)

        if self.price == 21:
            # wallet balance must now equal to 10_000 + the profit we made from previous trade
            previous_trade = self.trades[0]
            assert self.position.exchange.wallet_balance() == previous_trade.pnl + 10000
            # now that position is closed, available_margin should equal to wallet_balance*leverage
            assert self.position.exchange.available_margin() == self.position.exchange.wallet_balance() * 2 == self.available_margin
            assert self.balance == self.position.exchange.wallet_balance()
            assert self.balance*self.leverage == self.available_margin

    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty1 = utils.size_to_qty(2000, self.price+2)
        qty2 = utils.size_to_qty(2000, self.price+4)
        self.buy = [
            (qty1, self.price+2),
            (qty2, self.price+4),
        ]

    def update_position(self):
        if self.price == 20:
            self.liquidate()

    def go_short(self):
        pass

    def should_cancel(self):
        return False
