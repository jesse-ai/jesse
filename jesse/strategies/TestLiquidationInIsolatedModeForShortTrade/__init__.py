from jesse.strategies import Strategy
from jesse import utils


class TestLiquidationInIsolatedModeForShortTrade(Strategy):
    def on_open_position(self, order):
        assert round(self.position.liquidation_price, 2) == 14.96
        assert round(self.position.bankruptcy_price, 2) == 15

    def before(self):
        if self.index == 0:
            assert self.balance == 10000
            assert self.leverage == 2
            assert self.available_margin == 20000

        # the liquidation price is at $14.94 so at $15:
        if self.price == 15:
            # assert that we are liquidated by this point
            assert self.is_close
            assert self.balance == 0
            assert self.available_margin == 0

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return self.price == 10

    def go_long(self):
        pass

    def go_short(self):
        # utils.size_to_qty(self.available_margin, self.price) == 2000
        self.sell = 2000, self.price

    def should_cancel(self):
        return False
