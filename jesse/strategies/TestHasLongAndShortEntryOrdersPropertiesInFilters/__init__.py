from jesse.strategies import Strategy
import jesse.helpers as jh


class TestHasLongAndShortEntryOrdersPropertiesInFilters(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = [
            (1, 9),
            (1, 8),
        ]

    def should_short(self) -> bool:
        return self.price == 20

    def go_short(self):
        self.sell = [
            (1, 20),
            (1, 21),
        ]

    def filters(self) -> list:
        return [self.filter1]

    def filter1(self):
        if self.price == 10:
            assert self.has_long_entry_orders is True
            assert self.has_short_entry_orders is False
            assert self.average_entry_price == 8.5
            return self.average_entry_price == 8.5

        if self.price == 20:
            assert self.has_long_entry_orders is False
            assert self.has_short_entry_orders is True
            assert self.average_entry_price == 20.5
            return self.average_entry_price == 20.5

    def should_cancel(self):
        return self.price in [15, 25]
