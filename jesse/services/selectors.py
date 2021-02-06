from typing import List, Union, ValuesView, Optional, Any

from jesse.models import Order, SpotExchange, FuturesExchange, Position
from jesse.strategies import Strategy


def get_current_price(exchange: str, symbol: str) -> float:
    p = get_position(exchange, symbol)
    return p.current_price


def get_position(exchange: str, symbol: str) -> Position:
    from jesse.store import store
    key = '{}-{}'.format(exchange, symbol)
    return store.positions.storage.get(key, None)


def get_orders(exchange: str, symbol: str) -> List[Order]:
    from jesse.store import store
    return store.orders.get_orders(exchange, symbol)


def get_time() -> int:
    from jesse.store import store
    return store.app.time


def get_exchange(name: str) -> Union[SpotExchange, FuturesExchange]:
    from jesse.store import store
    return store.exchanges.storage.get(name, None)


def get_all_exchanges() -> ValuesView[Union[SpotExchange, FuturesExchange]]:
    from jesse.store import store
    return store.exchanges.storage.values()


def get_strategy(exchange: str, symbol: str) -> Strategy:
    from jesse.routes import router
    r = next(r for r in router.routes
             if r.exchange == exchange and r.symbol == symbol)
    return r.strategy


def get_route(exchange: str, symbol: str) -> Optional[Any]:
    from jesse.routes import router
    r = next(
        (r for r in router.routes if r.exchange == exchange and r.symbol == symbol),
        None)
    return r


def get_all_trading_routes() -> List[Any]:
    from jesse.routes import router
    return router.routes
