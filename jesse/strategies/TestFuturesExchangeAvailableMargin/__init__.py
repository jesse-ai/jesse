from jesse import utils
from jesse.strategies import Strategy


class TestFuturesExchangeAvailableMargin(Strategy):
    def before(self):
        if self.index == 0:
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            assert self.position.exchange.available_margin == 10000 == self.available_margin

        if self.price == 11:
            # wallet balance should have stayed the same while we haven't spent from it yet
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            # Adjusting available_margin calculation
            assert round(self.position.exchange.available_margin) == 10000 - (2000 / 2) == round(self.available_margin)

        if self.price == 12:
            # wallet balance should have stayed the same, no fee in this test
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            # available_margin should have stayed the same, not include reduce only orders
            assert round(self.position.exchange.available_margin) == 10000 - (2000 / 2) == round(self.available_margin)

        if self.price == 13:
            # wallet balance should have stayed the same, no fee in this test
            assert self.position.exchange.wallet_balance == 10000 == self.balance
            # Adjusting available_margin calculation considering unrealized profit and leverage
            # The leverage is applied to the PNL to reflect its impact on the available margin
            expected_margin = 10000 - (2000 / 2) + (self.position.pnl)
            assert round(self.position.exchange.available_margin) == round(expected_margin) == round(
                self.available_margin)

        if self.price == 21:
            # wallet balance now equals to 10_000 + profit from previous trade
            previous_trade = self.trades[0]
            assert self.position.exchange.wallet_balance == previous_trade.pnl + 10000
            # available_margin should equal to wallet_balance after position is closed
            assert self.available_margin == self.position.exchange.wallet_balance
            assert self.balance == self.position.exchange.wallet_balance
            assert self.balance == self.available_margin

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
