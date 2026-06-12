from typing import List

import fnc

from jesse.models.Order import Order
import jesse.helpers as jh


class OrdersState:
    def __init__(self) -> None:
        # used in simulation only
        self.to_execute = []

        self.storage = {}
        self.active_storage = {}

    def reset(self) -> None:
        """
        used for testing
        """
        for key in self.storage:
            self.storage[key].clear()
            self.active_storage[key].clear()

    def reset_trade_orders(self, exchange: str, symbol: str) -> None:
        """
        used after each completed trade
        """
        key = f'{exchange}-{symbol}'
        self.storage[key] = []
        self.active_storage[key] = []

    def add_order(self, order: Order) -> None:
        """Add order to in-memory state only"""
        key = f'{order.exchange}-{order.symbol}'

        if jh.is_live():
            # Check if order with same id already exists
            existing_order = fnc.find(lambda o: o.id == order.id, self.storage.get(key, []))
            if existing_order:
                return

            # Check if order with same exchange_id already exists (if exchange_id is set)
            if hasattr(order, 'exchange_id') and order.exchange_id:
                existing_exchange_order = fnc.find(lambda o: o.exchange_id == order.exchange_id, self.storage.get(key, []))
                if existing_exchange_order:
                    return

        self.storage[key].append(order)
        self.active_storage[key].append(order)

    def remove_order(self, order: Order) -> None:
        key = f'{order.exchange}-{order.symbol}'
        self.storage[key] = [
            o for o in self.storage[key] if o.id != order.id
        ]
        self.active_storage[key] = [
            o for o in self.active_storage[key] if o.id != order.id
        ]

    # # # # # # # # # # # # # # # # #
    # getters
    # # # # # # # # # # # # # # # # #
    def get_orders(self, exchange, symbol) -> List[Order]:
        key = f'{exchange}-{symbol}'
        return self.storage.get(key, [])

    def get_active_orders(self, exchange, symbol) -> List[Order]:
        key = f'{exchange}-{symbol}'
        return self.active_storage.get(key, [])

    def get_all_orders(self, exchange: str) -> List[Order]:
        return [
            o
            for key in self.storage
            for o in self.storage[key]
            if o.exchange == exchange
        ]

    def count_all_active_orders(self) -> int:
        c = 0
        for key in self.active_storage:
            if len(self.active_storage[key]) == 0:
                continue

            for o in self.active_storage[key]:
                if o.is_active:
                    c += 1
        return c

    def count_active_orders(self, exchange: str, symbol: str) -> int:
        orders = self.get_active_orders(exchange, symbol)

        return sum(bool(o.is_active) for o in orders)

    def count(self, exchange: str, symbol: str) -> int:
        return len(self.get_orders(exchange, symbol))

    def get_order_by_id(self, exchange: str, symbol: str, id: str, use_exchange_id: bool = False) -> Order:
        key = f'{exchange}-{symbol}'

        if use_exchange_id:
            return fnc.find(lambda o: o.exchange_id == id, self.storage[key])

        # make sure id (client_id) is not and empty string
        if id == '':
            return None

        return fnc.find(lambda o: id in str(o.id), reversed(self.storage[key]))
