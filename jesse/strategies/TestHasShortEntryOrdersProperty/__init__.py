from jesse.strategies import Strategy
import jesse.helpers as jh


class TestHasShortEntryOrdersProperty(Strategy):
    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_short(self) -> bool:
        return self.price in [10, 20]

    def go_short(self):
        if self.price == 10:
            self.sell = [
                (1, 9),
                (1, 8),
            ]

        if self.price == 20:
            self.sell = [
                (1, 20),
                (1, 19),
            ]

    def before(self) -> None:
        if self.price < 10:
            assert self.has_short_entry_orders is False
            assert self.has_long_entry_orders is False

        # when no orders have been filled
        if self.price == 11:
            assert self.has_short_entry_orders is True
            assert self.has_long_entry_orders is False
        # when entries are cancelled
        if self.price == 16:
            assert self.has_short_entry_orders is False
            assert self.has_long_entry_orders is False

        # when one order is filled and one is still active
        elif self.price == 21:
            assert self.has_short_entry_orders is True
            assert self.has_long_entry_orders is False
        # after the trade is closed
        elif self.price == 26:
            assert self.has_short_entry_orders is False
            assert self.has_long_entry_orders is False

    def should_cancel_entry(self):
        return self.price == 15

    def update_position(self) -> None:
        if self.price == 25:
            self.liquidate()

