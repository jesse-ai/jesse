from jesse.strategies import Strategy


class TestMultipleEntryOrdersUpdateEntryLongPositions(Strategy):
    def before(self) -> None:
        if self.price == 12:
            assert self.orders[0].type == 'MARKET'
            assert self.orders[0].status == 'EXECUTED'

            assert self.orders[1].type == 'LIMIT'
            assert self.orders[1].status == 'ACTIVE'

        if self.price == 15:
            assert self.orders[0].type == 'MARKET'
            assert self.orders[0].status == 'EXECUTED'
            assert self.orders[0].price == 10

            assert self.orders[1].type == 'LIMIT'
            assert self.orders[1].status == 'CANCELED'
            assert self.orders[2].type == 'LIMIT'
            assert self.orders[2].status == 'CANCELED'

            assert self.orders[3].type == 'MARKET'
            assert self.orders[3].status == 'EXECUTED'
            assert self.orders[3].price == 13

            assert self.orders[4].type == 'LIMIT'
            assert self.orders[4].status == 'ACTIVE'
            assert self.orders[4].price == 10

    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        self.buy = [
            (1, 10),
            (1, 9),
            (1, 8),
        ]

    def update_position(self) -> None:
        if self.price == 13:
            self.buy = [
                (1, 13),
                (1, 10),
            ]

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
