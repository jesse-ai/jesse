from jesse.strategies import Strategy


class TestCanCancelEntryOrdersAfterOpenPositionShort1(Strategy):
    def before(self) -> None:
        if self.price == 12:
            self._fake_order(0, 'MARKET', 'EXECUTED', 10)
            self._fake_order(1, 'STOP', 'ACTIVE', 9)
            self._fake_order(2, 'STOP', 'ACTIVE', 8)
        elif self.price == 15:
            self._fake_order(0, 'MARKET', 'EXECUTED', 10)
            assert self.orders[1].type == 'STOP'
            assert self.orders[1].status == 'CANCELED'
            assert self.orders[2].type == 'STOP'
            assert self.orders[2].status == 'CANCELED'

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
            self.sell = []

    def go_short(self):
        self.sell = [
            (1, 10),
            (1, 9),
            (1, 8),
        ]

    def should_cancel(self):
        return False
