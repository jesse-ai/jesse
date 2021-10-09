from jesse.strategies import Strategy
from jesse.models import Order


class TestPartiallyExecutedOrders1(Strategy):
    def before(self):
        if self.price == 12:
            o: Order = self._open_position_orders[0]
            order_dict = {
                'symbol': o.symbol,
                'side': o.side,
                'qty': o.qty,
                # let's fake that half of our position is filled
                'filled_qty': 1,
                'price': o.price,
                'exchange_id': None,
                'client_id': o.id,
                'status': o.status,
                'type': o.type
            }
            o.execute_partially(o, order_dict)

        if self.price == 20:
            self.liquidate()

    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        self.buy = 2, 8

    def go_short(self):
        pass

    def should_cancel(self):
        return False
