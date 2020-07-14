def get_current_price(exchange, symbol):
    """

    :param exchange:
    :param symbol:
    :return:
    """
    p = get_position(exchange, symbol)
    return p.current_price


def get_position(exchange, symbol):
    """

    :param exchange:
    :param symbol:
    :return:
    """
    from jesse.store import store
    key = '{}-{}'.format(exchange, symbol)
    return store.positions.storage.get(key, None)


def get_orders(exchange, symbol):
    """

    :param exchange:
    :param symbol:
    :return:
    """
    from jesse.store import store
    return store.orders.get_orders(exchange, symbol)


def get_time():
    """

    :return:
    """
    from jesse.store import store
    return store.app.time


def get_exchange(name):
    """

    :param name:
    :return:
    """
    from jesse.store import store
    return store.exchanges.storage.get(name, None)


def get_strategy(exchange, symbol):
    """

    :param exchange:
    :param symbol:
    :return:
    """
    from jesse.routes import router
    r = next(r for r in router.routes
             if r.exchange == exchange and r.symbol == symbol)
    return r.strategy


def get_route(exchange, symbol):
    """

    :param exchange:
    :param symbol:
    :return:
    """
    from jesse.routes import router
    r = next(
        (r for r in router.routes if r.exchange == exchange and r.symbol == symbol),
        None)
    return r
