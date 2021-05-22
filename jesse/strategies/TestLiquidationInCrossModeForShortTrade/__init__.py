import numpy as np

from jesse.strategies import Strategy


class TestLiquidationInCrossModeForShortTrade(Strategy):
    def on_open_position(self, order):
        # print(self.position.liquidation_price)
        # assert self.position.liquidation_price == 22.09
        assert np.isnan(self.position.liquidation_price)

    def before(self):
        if self.index == 0:
            assert self.balance == 10000
            assert self.leverage == 10
            assert self.available_margin == 10 * 10000
            assert self.position.mode == 'cross'

        # # the liquidation price is at $14.94 so at $15:
        # if self.price == 15:
        #     # assert that we are liquidated by this point
        #     print(self.balance)
        #     print(self.available_margin)
        #     assert self.is_close
        #     assert self.balance == 0
        #     assert self.available_margin == 0

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        if self.price == 20:
            return True

        return False

    def go_long(self):
        pass

    def go_short(self):
        qty = self.available_margin / self.price
        print('qty', qty)
        self.sell = qty, self.price

    def should_cancel(self):
        return False
