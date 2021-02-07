import threading

import jesse.helpers as jh
from jesse.models import Order


class API:
    def __init__(self) -> None:
        self.drivers = {}

        if not jh.is_live():
            self.initiate_drivers()

    def initiate_drivers(self) -> None:
        for e in jh.get_config('app.considering_exchanges'):
            if jh.is_live():
                def initiate_ws(exchange_name: str) -> None:
                    exchange_class = jh.get_config('app.live_drivers.{}'.format(exchange_name))
                    self.drivers[exchange_name] = exchange_class()

                threading.Thread(target=initiate_ws, args=[e]).start()
            else:
                from jesse.exchanges import Sandbox
                self.drivers[e] = Sandbox(e)

    def market_order(self, exchange: str, symbol: str, qty: float, current_price: float, side: str, role: str,
                     flags: str) -> Order:
        return self.drivers[exchange].market_order(symbol, qty, current_price, side, role, flags)

    def limit_order(self, exchange: str, symbol: str, qty: float, price: float, side: str, role: str,
                    flags: str) -> Order:
        return self.drivers[exchange].limit_order(symbol, qty, price, side, role, flags)

    def stop_order(self, exchange: str, symbol: str, qty: float, price: float, side: str, role: str,
                   flags: str) -> Order:
        return self.drivers[exchange].stop_order(symbol, qty, price, side, role, flags)

    def cancel_all_orders(self, exchange: str, symbol: str) -> bool:
        return self.drivers[exchange].cancel_all_orders(symbol)

    def cancel_order(self, exchange: str, symbol: str, order_id: str) -> bool:
        return self.drivers[exchange].cancel_order(symbol, order_id)


api = API()
