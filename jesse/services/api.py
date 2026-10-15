import threading
from typing import Union

import jesse.helpers as jh
from jesse.models.Order import Order
from jesse.services import logger


class API:
    def __init__(self) -> None:
        self.drivers = {}

        if not jh.is_live():
            self.initiate_drivers()

    def initiate_drivers(self) -> None:
        considering_exchanges = jh.get_config('app.considering_exchanges')

        # Driver construction requires the active route set.
        if not len(considering_exchanges):
            raise Exception('No exchange is available for initiating in the API class')

        for exchange_name in considering_exchanges:
            self.initiate_driver(exchange_name)

    def reset_drivers(self) -> None:
        """Discard driver instances owned by the completed runtime session."""
        self.drivers.clear()

    def initiate_driver(self, exchange_name: str) -> None:
        """Idempotently register the API driver for one exchange."""
        if exchange_name in self.drivers:
            return

        if jh.is_live():
            def initiate_ws(name: str) -> None:
                exchange_class = jh.get_config(f'app.live_drivers.{name}')
                self.drivers[name] = exchange_class()

            threading.Thread(target=initiate_ws, args=[exchange_name]).start()
        else:
            from jesse.exchanges import Sandbox
            self.drivers[exchange_name] = Sandbox(exchange_name)

    def market_order(
        self,
        exchange: str,
        symbol: str,
        qty: float,
        current_price: float,
        side: str,
        reduce_only: bool
    ) -> Union[Order, None]:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return None
        return self.drivers[exchange].market_order(symbol, qty, current_price, side, reduce_only)

    def limit_order(
        self,
        exchange: str,
        symbol: str,
        qty: float,
        price: float,
        side: str,
        reduce_only: bool
    ) -> Union[Order, None]:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return None
        return self.drivers[exchange].limit_order(symbol, qty, price, side, reduce_only)

    def stop_order(
        self, exchange: str,
        symbol: str,
        qty: float,
        price: float,
        side: str,
        reduce_only: bool
    ) -> Union[Order, None]:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return None
        return self.drivers[exchange].stop_order(symbol, qty, price, side, reduce_only)

    def cancel_all_orders(self, exchange: str, symbol: str) -> bool:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return False
        return self.drivers[exchange].cancel_all_orders(symbol)

    def cancel_order(self, exchange: str, symbol: str, order_id: str) -> bool:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return False
        return self.drivers[exchange].cancel_order(symbol, order_id)


api = API()
