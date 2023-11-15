from jesse.strategies import Strategy


class TestLiquidationInIsolatedModeForLongTrade(Strategy):
    def on_open_position(self, order):
        assert round(self.position.liquidation_price, 2) == 40.32

    def before(self):
        if self.price == 40:
            # assert that we are liquidated by this point
            assert self.is_close
            assert self.balance == 0
            assert self.available_margin == 0

    def should_long(self) -> bool:
        if self.index == 0:
            assert self.balance == 10000
            assert self.leverage == 2
            assert self.leveraged_available_margin == 20000
            assert self.available_margin == 10000
            assert self.position.mode == 'isolated'

        return self.price == 80

    def should_short(self) -> bool:
        return False

    def go_long(self):
        # go all in
        self.buy = 250, self.price

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
