import numpy as np

import jesse.helpers as jh
from jesse.config import config, reset_config
from jesse.store import store


def set_up():
    """

    """
    reset_config()
    config['app']['considering_candles'] = [('Sandbox', 'BTC-USD')]
    store.reset()
    store.tickers.init_storage()


def test_can_add_new_ticker():
    set_up()

    np.testing.assert_equal(store.tickers.get_tickers('Sandbox', 'BTC-USD'), np.zeros((0, 5)))

    # add first ticker
    t1 = np.array([jh.now_to_timestamp(), 1, 2, 3, 4], dtype=np.float64)
    store.tickers.add_ticker(t1, 'Sandbox', 'BTC-USD')
    np.testing.assert_equal(store.tickers.get_tickers('Sandbox', 'BTC-USD')[0], t1)

    # fake 1 second
    store.app.time += 1000

    # add second ticker
    t2 = np.array([jh.now_to_timestamp() + 1, 11, 22, 33, 44], dtype=np.float64)
    store.tickers.add_ticker(t2, 'Sandbox', 'BTC-USD')
    np.testing.assert_equal(store.tickers.get_tickers('Sandbox', 'BTC-USD'), np.array([t1, t2]))


def test_get_current_and_past_ticker():
    set_up()

    # add 4 tickers
    t1 = np.array([jh.now_to_timestamp(), 1, 2, 3, 4], dtype=np.float64)
    t2 = np.array([jh.now_to_timestamp() + 1000, 2, 2, 3, 4], dtype=np.float64)
    t3 = np.array([jh.now_to_timestamp() + 2000, 3, 2, 3, 4], dtype=np.float64)
    t4 = np.array([jh.now_to_timestamp() + 3000, 4, 2, 3, 4], dtype=np.float64)
    store.tickers.add_ticker(t1, 'Sandbox', 'BTC-USD')
    store.app.time += 1000
    store.tickers.add_ticker(t2, 'Sandbox', 'BTC-USD')
    store.app.time += 1000
    store.tickers.add_ticker(t3, 'Sandbox', 'BTC-USD')
    store.app.time += 1000
    store.tickers.add_ticker(t4, 'Sandbox', 'BTC-USD')
    np.testing.assert_equal(store.tickers.get_tickers('Sandbox', 'BTC-USD'), np.array([t1, t2, t3, t4]))

    # get the previous one
    np.testing.assert_equal(store.tickers.get_past_ticker('Sandbox', 'BTC-USD', 1), t3)

    # get current
    np.testing.assert_equal(store.tickers.get_current_ticker('Sandbox', 'BTC-USD'), t4)
