from jesse.strategies import Strategy
from pprint import pprint
import jesse.helpers as jh


class TestMultipleEntryOrdersUpdateEntryShortPositions(Strategy):
    def before(self) -> None:
        if self.price == 12:
            assert self.orders[0].type == 'MARKET'
            assert self.orders[0].status == 'EXECUTED'
            assert self.orders[0].price == 10

            assert self.orders[1].type == 'LIMIT'
            assert self.orders[1].status == 'ACTIVE'
            assert self.orders[1].price == 20

        if self.price == 15:
            assert self.orders[0].type == 'MARKET'
            assert self.orders[0].status == 'EXECUTED'
            assert self.orders[0].price == 10

            assert self.orders[1].type == 'LIMIT'
            assert self.orders[1].status == 'CANCELED'
            assert self.orders[1].price == 20
            assert self.orders[2].type == 'LIMIT'
            assert self.orders[2].status == 'CANCELED'
            assert self.orders[2].price == 21

            assert self.orders[3].type == 'MARKET'
            assert self.orders[3].status == 'EXECUTED'
            assert self.orders[3].price == 13

            assert self.orders[4].type == 'LIMIT'
            assert self.orders[4].status == 'ACTIVE'
            assert self.orders[4].price == 22

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

    def should_cancel_entry(self):
        return False
