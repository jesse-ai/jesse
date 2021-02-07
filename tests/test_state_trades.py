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
    store.trades.init_storage()


def test_can_add_add_trade():
    set_up()

    np.testing.assert_equal(store.trades.get_trades('Sandbox', 'BTC-USD'), np.zeros((0, 6)))

    # add first trade
    t1 = np.array([jh.now_to_timestamp(), 100, 2, 1], dtype=np.float64)
    t2 = np.array([jh.now_to_timestamp(), 98, 2, 1], dtype=np.float64)
    t3 = np.array([jh.now_to_timestamp(), 98, 2, 0], dtype=np.float64)
    t4 = np.array([jh.now_to_timestamp(), 98, 2, 0], dtype=np.float64)
    t5 = np.array([jh.now_to_timestamp(), 98, 2, 0], dtype=np.float64)
    store.trades.add_trade(t1, 'Sandbox', 'BTC-USD')
    store.trades.add_trade(t2, 'Sandbox', 'BTC-USD')
    store.trades.add_trade(t3, 'Sandbox', 'BTC-USD')
    store.trades.add_trade(t4, 'Sandbox', 'BTC-USD')
    store.trades.add_trade(t5, 'Sandbox', 'BTC-USD')

    assert len(store.trades.get_trades('Sandbox', 'BTC-USD')) == 0

    t6 = np.array([jh.now_to_timestamp() + 1000, 98, 2, 1], dtype=np.float64)
    store.trades.add_trade(t6, 'Sandbox', 'BTC-USD')

    assert len(store.trades.get_trades('Sandbox', 'BTC-USD')) == 1

    np.testing.assert_equal(store.trades.get_current_trade('Sandbox', 'BTC-USD'), np.array([
        jh.now_to_timestamp(),
        # price
        (100 * 2 + 98 * 2 + 98 * 2 + 98 * 2 + 98 * 2) / 10,
        # buy_qty
        4,
        # sell_qty
        6,
        # buy_count
        2,
        # sell_count
        3
    ]))

    # add another after two seconds
    t7 = np.array([jh.now_to_timestamp() + 3000, 98, 2, 1], dtype=np.float64)
    store.trades.add_trade(t7, 'Sandbox', 'BTC-USD')

    np.testing.assert_equal(store.trades.get_current_trade('Sandbox', 'BTC-USD'), np.array([
        jh.now_to_timestamp() + 1000,
        # price
        98,
        # buy_qty
        2,
        # sell_qty
        0,
        # buy_count
        1,
        # sell_count
        0
    ]))

    # test get_past_trade
    np.testing.assert_equal(store.trades.get_past_trade('Sandbox', 'BTC-USD', 1), np.array([
        jh.now_to_timestamp(),
        # price
        (100 * 2 + 98 * 2 + 98 * 2 + 98 * 2 + 98 * 2) / 10,
        # buy_qty
        4,
        # sell_qty
        6,
        # buy_count
        2,
        # sell_count
        3
    ]))

    # test get_trades
    np.testing.assert_equal(store.trades.get_trades('Sandbox', 'BTC-USD'), np.array([
        [
            jh.now_to_timestamp(),
            # price
            (100 * 2 + 98 * 2 + 98 * 2 + 98 * 2 + 98 * 2) / 10,
            # buy_qty
            4,
            # sell_qty
            6,
            # buy_count
            2,
            # sell_count
            3
        ],
        [
            jh.now_to_timestamp() + 1000,
            # price
            98,
            # buy_qty
            2,
            # sell_qty
            0,
            # buy_count
            1,
            # sell_count
            0
        ]
    ]))
