from typing import List, ValuesView, Optional, Any


def get_current_price(exchange: str, symbol: str) -> float:
    if exchange is None or symbol is None:
        raise ValueError(f"exchange and symbol cannot be None. exchange: {exchange}, symbol: {symbol}")

    p = get_position(exchange, symbol)
    return p.current_price


def get_position(exchange: str, symbol: str) -> Any:
    if exchange is None or symbol is None:
        raise ValueError(f"exchange and symbol cannot be None. exchange: {exchange}, symbol: {symbol}")

    from jesse.store import store
    key = f'{exchange}-{symbol}'
    return store.positions.storage.get(key, None)


def get_orders(exchange: str, symbol: str) -> List[Any]:
    if exchange is None or symbol is None:
        raise ValueError(f"exchange and symbol cannot be None. exchange: {exchange}, symbol: {symbol}")

    from jesse.store import store
    return store.orders.get_orders(exchange, symbol)


def get_time() -> int:
    from jesse.store import store
    return store.app.time


def get_exchange(name: str) -> Any:
    if name is None:
        raise ValueError(f"name cannot be None. name: {name}")

    from jesse.store import store
    return store.exchanges.storage.get(name, None)


def get_trading_exchange():
    """
    since we now only allow trading from one exchange at a time, this is the only one that we're gonna need
    """
    first_trading_route = get_all_trading_routes()[0]
    return get_exchange(first_trading_route.exchange)


def get_all_exchanges() -> ValuesView[Any]:
    from jesse.store import store
    return store.exchanges.storage.values()


def get_strategy(exchange: str, symbol: str) -> Any:
    if exchange is None or symbol is None:
        raise ValueError(f"exchange and symbol cannot be None. exchange: {exchange}, symbol: {symbol}")

    from jesse.routes import router
    r = next(r for r in router.routes
             if r.exchange == exchange and r.symbol == symbol)
    return r.strategy


def get_route(exchange: str, symbol: str) -> Optional[Any]:
    if exchange is None or symbol is None:
        raise ValueError(f"exchange and symbol cannot be None. exchange: {exchange}, symbol: {symbol}")

    from jesse.routes import router
    return next(
        (
            r
            for r in router.routes
            if r.exchange == exchange and r.symbol == symbol
        ),
        None,
    )


def get_all_trading_routes() -> List[Any]:
    from jesse.routes import router
    return router.routes


def get_all_extra_routes() -> List[Any]:
    from jesse.routes import router
    return router.formatted_extra_routes


def get_all_routes() -> List[Any]:
    from jesse.routes import router
    return router.all_formatted_routes
