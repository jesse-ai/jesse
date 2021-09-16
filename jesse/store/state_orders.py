from typing import List

import pydash

from jesse.config import config
from jesse.models import Order


class OrdersState:
    def __init__(self) -> None:
        # used in simulation only
        self.to_execute = []

        self.storage = {}

        for exchange in config['app']['trading_exchanges']:
            for symbol in config['app']['trading_symbols']:
                key = f'{exchange}-{symbol}'
                self.storage[key] = []

    def reset(self) -> None:
        for key in self.storage:
            self.storage[key].clear()

    def add_order(self, order: Order) -> None:
        key = f'{order.exchange}-{order.symbol}'
        self.storage[key].append(order)

    def remove_order(self, order: Order) -> None:
        key = f'{order.exchange}-{order.symbol}'
        self.storage[key] = [
            o for o in self.storage[key] if o.id != order.id
        ]

    # getters
    def get_orders(self, exchange, symbol) -> List[Order]:
        key = f'{exchange}-{symbol}'
        return self.storage.get(key, [])

    def count_all_active_orders(self) -> int:
        c = 0
        for key in self.storage:
            if len(self.storage[key]):
                for o in self.storage[key]:
                    if o.is_active:
                        c += 1
        return c

    def count_active_orders(self, exchange: str, symbol: str) -> int:
        orders = self.get_orders(exchange, symbol)

        return sum(bool(o.is_active) for o in orders)

    def count(self, exchange: str, symbol: str) -> int:
        return len(self.get_orders(exchange, symbol))

    def get_order_by_id(self, exchange: str, symbol: str, id: str, use_exchange_id: bool = False) -> Order:
        key = f'{exchange}-{symbol}'

        if use_exchange_id:
            return pydash.find(self.storage[key], lambda o: o.exchange_id == id)

        return pydash.find(self.storage[key], lambda o: o.id == id)

    def execute_pending_market_orders(self) -> None:
        if not self.to_execute:
            return

        for o in self.to_execute:
            o.execute()

        self.to_execute = []
