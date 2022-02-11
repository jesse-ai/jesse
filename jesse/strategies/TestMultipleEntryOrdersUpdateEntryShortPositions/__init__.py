from jesse.strategies import Strategy
from pprint import pprint
import jesse.helpers as jh


class TestMultipleEntryOrdersUpdateEntryShortPositions(Strategy):
    def before(self) -> None:
        if self.price == 12:
            self._fake_order(0, 'MARKET', 'EXECUTED', 10)
            self._fake_order(1, 'LIMIT', 'ACTIVE', 20)
        elif self.price == 15:
            self._fake_order(0, 'MARKET', 'EXECUTED', 10)
            self._fake_order(1, 'LIMIT', 'CANCELED', 20)
            self._fake_order(2, 'LIMIT', 'CANCELED', 21)
            self._fake_order(3, 'MARKET', 'EXECUTED', 13)
            self._fake_order(4, 'LIMIT', 'ACTIVE', 22)

    def _fake_order(self, i, type, status, price):
        assert self.orders[i].type == type
        assert self.orders[i].status == status
        assert self.orders[i].price == price

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return self.price == 10

    def go_long(self):
        pass

    def update_position(self) -> None:
        if self.price == 13:
            self.sell = [
                (1, 13),
                (1, 22),
            ]

    def go_short(self):
        self.sell = [
            (1, 10),
            (1, 20),
            (1, 21),
        ]

    def should_cancel(self):
        return False
