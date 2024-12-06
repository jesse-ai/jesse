from typing import List

import fnc

from jesse.config import config
from jesse.models import Order
from jesse.services import selectors
import jesse.helpers as jh


class OrdersState:
    def __init__(self) -> None:
        # used in simulation only
        self.to_execute = []

        self.storage = {}
        self.active_storage = {}

        for exchange in config['app']['trading_exchanges']:
            for symbol in config['app']['trading_symbols']:
                key = f'{exchange}-{symbol}'
                self.storage[key] = []
                self.active_storage[key] = []

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
        key = f'{order.exchange}-{order.symbol}'
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

    def execute_pending_market_orders(self) -> None:
        if not self.to_execute:
            return

        for o in self.to_execute:
            o.execute()

        self.to_execute = []

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

        return fnc.find(lambda o: id in o.id, reversed(self.storage[key]))

    def get_entry_orders(self, exchange: str, symbol: str) -> List[Order]:
        # return all orders if position is not opened yet
        p = selectors.get_position(exchange, symbol)
        if p.is_close:
            return self.get_orders(exchange, symbol).copy()

        all_orders = self.get_active_orders(exchange, symbol)
        p_side = jh.type_to_side(p.type)
        entry_orders = [o for o in all_orders if (o.side == p_side and not o.is_canceled)]

        return entry_orders

    def get_exit_orders(self, exchange: str, symbol: str) -> List[Order]:
        """
        excludes cancel orders but includes executed orders
        """
        all_orders = self.get_orders(exchange, symbol)
        # return empty if no orders
        if len(all_orders) == 0:
            return []
        # return empty if position is not opened yet
        p = selectors.get_position(exchange, symbol)
        if p.is_close:
            return []
        else:
            exit_orders = [o for o in all_orders if o.side != jh.type_to_side(p.type)]

        # exclude cancelled orders
        exit_orders = [o for o in exit_orders if not o.is_canceled]

        return exit_orders

    def get_active_exit_orders(self, exchange: str, symbol: str) -> List[Order]:
        """
        excludes cancel orders but includes executed orders
        """
        all_orders = self.get_active_orders(exchange, symbol)
        # return empty if no orders
        if len(all_orders) == 0:
            return []
        # return empty if position is not opened yet
        p = selectors.get_position(exchange, symbol)
        if p.is_close:
            return []
        else:
            exit_orders = [o for o in all_orders if o.side != jh.type_to_side(p.type)]

        # exclude cancelled orders
        exit_orders = [o for o in exit_orders if not o.is_canceled]

        return exit_orders

    def update_active_orders(self, exchange: str, symbol: str):
        key = f'{exchange}-{symbol}'
        active_orders = [
            order
            for order in self.get_active_orders(exchange, symbol)
            if not order.is_canceled and not order.is_executed
        ]
        self.active_storage[key] = active_orders
