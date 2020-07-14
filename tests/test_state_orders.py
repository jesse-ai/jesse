from jesse.config import config, reset_config
from jesse.enums import exchanges
from jesse.factories import fake_order
from jesse.store import store


def set_up():
    """

    """
    reset_config()
    config['app']['trading_exchanges'] = [exchanges.SANDBOX, exchanges.BITFINEX]
    config['app']['trading_symbols'] = ['BTCUSD', 'ETHUSD']
    store.reset()


def test_add_new_order():
    set_up()

    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'ETHUSD'})
    o2 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'ETHUSD'})
    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.storage['Sandbox-ETHUSD'] == [o1, o2]


def test_order_state_init():
    set_up()

    assert len(store.orders.storage.keys()) == 4


def test_state_order_count():
    set_up()

    assert store.orders.count(exchanges.SANDBOX, 'BTCUSD') == 0
    store.orders.add_order(fake_order())
    assert store.orders.count(exchanges.SANDBOX, 'BTCUSD') == 1
    store.orders.add_order(fake_order())
    assert store.orders.count(exchanges.SANDBOX, 'BTCUSD') == 2


def test_state_order_get_order_by_id():
    set_up()

    o0 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'ETHUSD'})
    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'ETHUSD'})
    o2 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'ETHUSD'})

    store.orders.get_order_by_id(exchanges.SANDBOX, 'ETHUSD', o2.id)

    # return None if does not exist
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'ETHUSD',
                                        o0.id) == None

    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.get_order_by_id(exchanges.SANDBOX, 'ETHUSD',
                                        o2.id) == o2
def test_state_order_get_orders():
    set_up()

    o1 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'ETHUSD'})
    o2 = fake_order({'exchange': exchanges.SANDBOX, 'symbol': 'ETHUSD'})
    store.orders.add_order(o1)
    store.orders.add_order(o2)
    assert store.orders.get_orders(exchanges.SANDBOX,
                                   'ETHUSD') == [o1, o2]


