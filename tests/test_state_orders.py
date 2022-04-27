from jesse.config import config, reset_config
from jesse.enums import exchanges
from jesse.factories import fake_order
from jesse.store import store
from jesse.routes import router
import jesse.helpers as jh


def set_up():
    reset_config()
    config['app']['trading_exchanges'] = [exchanges.SANDBOX]
    config['app']['trading_symbols'] = ['BTC-USD']
    routes = [
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD', 'timeframe': '1m', 'strategy': 'TestVanillaStrategy'}
    ]
    router.initiate(routes)


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

    # return None if does not exist
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD',
                                        o0.id) is None

    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'BTC-USD',
                                        o2.id) == o2


def test_state_order_get_orders():
    set_up()

    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    o2 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD'})
    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.get_orders(exchanges.SANDBOX, 'BTC-USD') == [o1, o2]
