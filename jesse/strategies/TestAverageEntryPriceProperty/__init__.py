from jesse.strategies import Strategy
import jesse.helpers as jh


class TestAverageEntryPriceProperty(Strategy):
    def should_long(self):
        return self.price in [1, 5, 10]

    def update_position(self) -> None:
        if self.price in [3, 7]:
            self.liquidate()

    def go_long(self):
        if self.price == 1:
            self.buy = [
                (1, 2),
                (1, 3),
            ]

        if self.price == 5:
            self.buy = [
                (1, 5),
                (1, 7),
            ]

        if self.price == 10:
            self.buy = [
                (1, 12),
                (1, 13),
            ]

    def before(self) -> None:
        # when both orders have been filled
        if self.price == 3:
            assert self.average_entry_price == 2.5

        # when only one order has been filled
        if self.price == 6:
            assert self.average_entry_price == 6

        # when no orders have been filled
        if self.price == 11:
            assert self.average_entry_price == 12.5

    def should_cancel(self):
        return False

    def should_short(self):
        return False

    def go_short(self):
        pass
