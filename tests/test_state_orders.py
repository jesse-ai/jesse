from jesse.config import config, reset_config
from jesse.enums import exchanges
from jesse.factories import fake_order
from jesse.store import store
from jesse.routes import router
from jesse.services import exchange_service, order_service, position_service
import jesse.helpers as jh


def set_up():
    reset_config()
    config['app']['trading_exchanges'] = [exchanges.SANDBOX]
    config['app']['trading_symbols'] = ['BTC-USD']
    routes = [
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD', 'timeframe': '1m', 'strategy': 'TestVanillaStrategy'}
    ]
    router.initiate(routes)
    # reset store
    store.reset() 
    # initialize exchanges state
    exchange_service.initialize_exchanges_state()
    # initialize orders state
    order_service.initialize_orders_state()
    # initialize positions state
    position_service.initialize_positions_state()


def test_add_new_order():
    set_up()

    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    o2 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.storage['Sandbox-BTC-USD'] == [o1, o2]


def test_state_order_count():
    set_up()

    assert store.orders.count(exchanges.SANDBOX, 'BTC-USD') == 0
    store.orders.add_order(fake_order())
    assert store.orders.count(exchanges.SANDBOX, 'BTC-USD') == 1
    store.orders.add_order(fake_order())
    assert store.orders.count(exchanges.SANDBOX, 'BTC-USD') == 2


def test_state_order_get_order_by_id():
    set_up()

    o0 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    o2 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})

    store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD', o2.id)

    # return None if it does not exist
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD', o0.id) is None

    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD', o2.id) == o2


def test_state_order_get_order_by_id_with_int_id():
    # regression #820: get_order_by_id must not crash when the client_id is an int
    set_up()

    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    o1.id = 'algo-987654-xyz'  # controlled id with a numeric run to match against
    store.orders.add_order(o1)

    # an int id that isn't present must return None (not raise)
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD', 123456789) is None

    # an int id whose string form is a substring of an existing order's id still matches
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD', 987654) == o1

    # None is treated like an empty id -> None, not a crash
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD', None) is None


def test_state_order_get_orders():
    set_up()

    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    o2 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.get_orders(exchanges.SANDBOX, 'BTC-USD') == [o1, o2]
