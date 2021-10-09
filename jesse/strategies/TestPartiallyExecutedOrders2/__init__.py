from jesse import utils
from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse.store import store
from jesse.models import Order


class TestPartiallyExecutedOrders2(Strategy):
    def before(self):
        if self.price == 15:
            o: Order = self._close_position_orders[0]
            order_dict = {
                'symbol': o.symbol,
                'side': o.side,
                'qty': o.qty,
                # let's fake that half of our position is filled
                'filled_qty': 1,
                # o.price = 20
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
        # price: 10
        self.buy = 2, self.price
        self.take_profit = 2, 20

    def go_short(self):
        pass

    def should_cancel(self):
        return False
