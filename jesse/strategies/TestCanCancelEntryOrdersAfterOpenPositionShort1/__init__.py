from jesse.strategies import Strategy


class TestCanCancelEntryOrdersAfterOpenPositionShort1(Strategy):
    def before(self) -> None:
        if self.price == 12:
            assert self.orders[0].type == 'MARKET'
            assert self.orders[0].status == 'EXECUTED'
            assert self.orders[0].price == 10

            assert self.orders[1].type == 'STOP'
            assert self.orders[1].status == 'ACTIVE'
            assert self.orders[1].price == 9

            assert self.orders[2].type == 'STOP'
            assert self.orders[2].status == 'ACTIVE'
            assert self.orders[2].price == 8

        if self.price == 15:
            assert self.orders[0].type == 'MARKET'
            assert self.orders[0].status == 'EXECUTED'
            assert self.orders[0].price == 10

            assert self.orders[1].type == 'STOP'
            assert self.orders[1].status == 'CANCELED'
            assert self.orders[2].type == 'STOP'
            assert self.orders[2].status == 'CANCELED'

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

    def should_cancel_entry(self):
        return False
