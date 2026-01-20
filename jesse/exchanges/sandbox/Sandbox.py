from jesse.models.Order import Order
import jesse.helpers as jh
from typing import List
from jesse.enums import order_types
from jesse.exchanges.exchange import Exchange
from jesse.store import store
from jesse.services import order_service


class Sandbox(Exchange):
    def __init__(self, name='Sandbox'):
        super().__init__()
        self.name = name

    def market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> Order:
        return order_service.create_order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.MARKET,
            'reduce_only': reduce_only,
            'qty': jh.prepare_qty(qty, side),
            'price': current_price,
        })

    def limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> Order:
        return order_service.create_order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.LIMIT,
            'reduce_only': reduce_only,
            'qty': jh.prepare_qty(qty, side),
            'price': price,
        })

    def stop_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> Order:
        return order_service.create_order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.STOP,
            'reduce_only': reduce_only,
            'qty': jh.prepare_qty(qty, side),
            'price': price,
        })

    def cancel_all_orders(self, symbol: str) -> List[Order]:
        orders: list[Order] = store.orders.get_active_orders(self.name, symbol)

        canceled_orders: List[Order] = []
        for o in orders:
            order_service.cancel_order(o)
            canceled_orders.append(o)

        if not jh.is_unit_testing():
            store.orders.storage[f'{self.name}-{symbol}'].clear()

        return canceled_orders
        
    def cancel_order(self, symbol: str, order_id: str) -> None:
        order = store.orders.get_order_by_id(self.name, symbol, order_id)
        order_service.cancel_order(order)

    def _fetch_precisions(self) -> None:
        pass
