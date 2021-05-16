from jesse.strategies import Strategy


class TestLiquidationInCrossMode(Strategy):
    def on_open_position(self, order):
        assert self.position.liquidation_price == 14.94

    def before(self):
        # the liquidation price is at $14.94 so at $15:
        if self.price == 15:
            # assert that we are liquidated by this point
            print(self.balance)
            print(self.available_margin)
            assert self.is_close
            assert self.balance == 0
            assert self.available_margin == 0

    def should_long(self) -> bool:
        if self.index == 0:
            assert self.balance == 10000
            assert self.leverage == 2
            assert self.available_margin == 20000

        return False

    def should_short(self) -> bool:
        if self.price == 10:
            return True

        return False

    def go_long(self):
        pass

    def go_short(self):
        self.sell = 2000, self.price

    def should_cancel(self):
        return False
