def get_current_price(exchange, symbol):
    p = get_position(exchange, symbol)
    return p.current_price


def get_position(exchange, symbol):
    from jesse.store import store
    key = '{}-{}'.format(exchange, symbol)
    return store.positions.storage.get(key, None)


def get_orders(exchange, symbol):
    from jesse.store import store
    return store.orders.get_orders(exchange, symbol)


def get_time():
    from jesse.store import store
    return store.app.time


def get_exchange(name):
    from jesse.store import store
    return store.exchanges.storage.get(name, None)


def get_all_exchanges():
    from jesse.store import store
    return store.exchanges.storage.values()


def get_strategy(exchange, symbol):
    from jesse.routes import router
    r = next(r for r in router.routes
             if r.exchange == exchange and r.symbol == symbol)
    return r.strategy


def get_route(exchange, symbol):
    from jesse.routes import router
    r = next(
        (r for r in router.routes if r.exchange == exchange and r.symbol == symbol),
        None)
    return r


def get_all_trading_routes():
    from jesse.routes import router
    return router.routes
