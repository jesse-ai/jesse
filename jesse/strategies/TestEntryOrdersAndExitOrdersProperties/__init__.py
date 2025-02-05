from jesse.strategies import Strategy
import jesse.helpers as jh


class TestEntryOrdersAndExitOrdersProperties(Strategy):
    def should_long(self):
        return self.price in [10, 25, 30]

    def go_long(self):
        if self.price == 10:
            self.buy = [
                (1, 10),
                (2, 9),
                (3, 8),
            ]
            self.stop_loss = 1, 5
        elif self.price == 25:
            self.buy = 1, 28
        elif self.price == 30:
            self.buy = [
                # stop
                (1, 31),
                # market
                (1, 30),
                # limit
                (1, 29),
            ]
            self.take_profit = [
                (1, 35),
                (1, 36),
                (1, 37),
            ]
            self.stop_loss = 3, 25

    def should_cancel_entry(self):
        # cancel second position entry attempt
        if self.price == 27:
            return True

        return False

    def update_position(self) -> None:
        if self.price == 20:
            self.liquidate()

    def before(self) -> None:
        if self.price == 11:
            # entry orders
            assert len(self.entry_orders) == 3
            assert self.entry_orders[0].price == 10
            assert self.entry_orders[0].qty == 1
            assert self.entry_orders[0].is_executed
            assert self.entry_orders[1].price == 9
            assert self.entry_orders[1].qty == 2
            assert self.entry_orders[1].is_active
            assert self.entry_orders[2].price == 8
            assert self.entry_orders[2].qty == 3
            assert self.entry_orders[2].is_active
            # exit orders
            assert len(self.exit_orders) == 1
            assert self.exit_orders[0].price == 5
            assert self.exit_orders[0].qty == -1
            assert self.exit_orders[0].is_active
            assert self.exit_orders[0].type == 'STOP'

        if self.price == 21:
            # entry orders
            assert len(self.entry_orders) == 0
            # exit orders
            assert len(self.exit_orders) == 0

        # after entry orders are submitted for the SECOND time
        if self.price == 26:
            # entry orders
            assert len(self.entry_orders) == 1
            assert self.entry_orders[0].price == 28
            assert self.entry_orders[0].qty == 1
            assert self.entry_orders[0].is_active
            assert self.entry_orders[0].type == 'STOP'
            # exit orders
            assert len(self.exit_orders) == 0

        if self.price == 28:
            assert len(self.entry_orders) == 0
            assert len(self.exit_orders) == 0

        # TODO: test for a third time while exit orders are also submitted
        if self.price == 31:
            # entry orders
            assert len(self.entry_orders) == 3
            assert self.entry_orders[0].price == 31
            assert self.entry_orders[0].qty == 1
            assert self.entry_orders[0].is_executed
            assert self.entry_orders[1].price == 30
            assert self.entry_orders[1].qty == 1
            assert self.entry_orders[1].is_executed
            assert self.entry_orders[2].price == 29
            assert self.entry_orders[2].qty == 1
            assert self.entry_orders[2].is_active

            # exit orders
            assert len(self.exit_orders) == 4

            assert self.exit_orders[0].price == 25
            assert self.exit_orders[0].qty == -3
            assert self.exit_orders[0].is_active
            assert self.exit_orders[0].type == 'STOP'

            assert self.exit_orders[1].price == 35
            assert self.exit_orders[1].qty == -1
            assert self.exit_orders[1].is_active
            assert self.exit_orders[1].type == 'LIMIT'

            assert self.exit_orders[2].price == 36
            assert self.exit_orders[2].qty == -1
            assert self.exit_orders[2].is_active
            assert self.exit_orders[2].type == 'LIMIT'

            assert self.exit_orders[3].price == 37
            assert self.exit_orders[3].qty == -1
            assert self.exit_orders[3].is_active
            assert self.exit_orders[3].type == 'LIMIT'
            
