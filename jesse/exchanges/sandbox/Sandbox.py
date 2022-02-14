import jesse.helpers as jh
from jesse.enums import order_types
from jesse.exchanges.exchange import Exchange
from jesse.models import Order
from jesse.store import store
from typing import Union

class Sandbox(Exchange):
    def __init__(self, name='Sandbox'):
        super().__init__()
        self.name = name

    def market_order(self, symbol: str, qty: float, current_price: float, side: str, role: str, flags: list) -> Order:
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.MARKET,
            'flag': self.get_exec_inst(flags),
            'qty': jh.prepare_qty(qty, side),
            'price': current_price,
            'role': role
        })

        store.orders.add_order(order)

        store.orders.to_execute.append(order)

        return order

    def limit_order(self, symbol: str, qty: float, price: float, side: str, role: str, flags: list) -> Order:
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.LIMIT,
            'flag': self.get_exec_inst(flags),
            'qty': jh.prepare_qty(qty, side),
            'price': price,
            'role': role
        })

        store.orders.add_order(order)

        return order

    def stop_order(self, symbol: str, qty: float, price: float, side: str, role: str, flags: list) -> Order:
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.STOP,
            'flag': self.get_exec_inst(flags),
            'qty': jh.prepare_qty(qty, side),
            'price': price,
            'role': role
        })

        store.orders.add_order(order)

        return order

    def cancel_all_orders(self, symbol: str) -> None:
        orders = filter(lambda o: o.is_new,
                        store.orders.get_orders(self.name, symbol))

        for o in orders:
            o.cancel()

        if not jh.is_unit_testing():
            store.orders.storage[f'{self.name}-{symbol}'].clear()

    def cancel_order(self, symbol: str, order_id: str) -> None:
        store.orders.get_order_by_id(self.name, symbol, order_id).cancel()

    def get_exec_inst(self, flags: list) -> Union[str, None]:
        if flags:
            return flags[0]
        return None

    def _fetch_precisions(self) -> None:
        pass
