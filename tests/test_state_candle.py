import numpy as np

from jesse.config import config, reset_config
from jesse.factories import fake_candle, range_candles
from jesse.services.candle import generate_candle_from_one_minutes
from jesse.store import store
import jesse.helpers as jh


def set_up():
    reset_config()
    from jesse.routes import router
    router.set_routes([
        {'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '1m', 'strategy': 'Test01'}
    ])
    router.set_extra_candles([{'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '5m'}])
    config['app']['considering_timeframes'] = ['1m', '5m']
    config['app']['considering_symbols'] = ['BTC-USD']
    config['app']['considering_exchanges'] = ['Sandbox']
    store.reset(True)
    store.candles.init_storage()


def test_batch_add_candles():
    set_up()

    assert len(store.candles.get_candles('Sandbox', 'BTC-USD', '1m')) == 0

    # create 100 candles
    candles_to_add = range_candles(100)
    assert len(candles_to_add) == 100

    store.candles.batch_add_candle(candles_to_add, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(store.candles.get_candles('Sandbox', 'BTC-USD', '1m'), candles_to_add)


def test_can_add_new_candle():
    set_up()

    np.testing.assert_equal(store.candles.get_candles('Sandbox', 'BTC-USD', '1m'), np.zeros((0, 6)))

    c1 = fake_candle()
    store.candles.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(store.candles.get_candles('Sandbox', 'BTC-USD', '1m')[0], c1)
    # try to add duplicate
    store.candles.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')
    # assert to make sure it's the same
    np.testing.assert_equal(store.candles.get_candles('Sandbox', 'BTC-USD', '1m')[0], c1)

    c2 = fake_candle()
    store.candles.add_candle(c2, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(store.candles.get_candles('Sandbox', 'BTC-USD', '1m'), np.array([c1, c2]))


def test_get_candles_including_forming():
    set_up()

    candles_to_add = range_candles(14)
    store.candles.batch_add_candle(candles_to_add, 'Sandbox', 'BTC-USD', '1m')
    store.candles.add_candle(
        generate_candle_from_one_minutes(
            '5m', candles_to_add[0:5], False
        ),
        'Sandbox', 'BTC-USD', '5m'
    )
    store.candles.add_candle(
        generate_candle_from_one_minutes(
            '5m', candles_to_add[5:10], False
        ),
        'Sandbox', 'BTC-USD', '5m'
    )

    assert len(store.candles.get_candles('Sandbox', 'BTC-USD', '5m')) == 3
    assert len(store.candles.get_candles('Sandbox', 'BTC-USD', '1m')) == 14

    candles = store.candles.get_candles('Sandbox', 'BTC-USD', '5m')
    assert candles[0][0] == candles_to_add[0][0]
    assert candles[-1][2] == candles_to_add[13][2]
    assert candles[-1][0] == candles_to_add[10][0]

    # add third one while still a forming candle. Now since
    # we already have forming, get_candles() must not
    # append another forming candle to the end.
    store.candles.add_candle(
        generate_candle_from_one_minutes(
            '5m', candles_to_add[10:14], True
        ),
        'Sandbox', 'BTC-USD', '5m'
    )

    assert len(store.candles.get_candles('Sandbox', 'BTC-USD', '5m')) == 3
    assert candles[-1][2] == candles_to_add[13][2]
    assert candles[-1][0] == candles_to_add[10][0]


def test_get_forming_candle():
    set_up()

    candles_to_add = range_candles(13)
    store.candles.batch_add_candle(candles_to_add[0:4], 'Sandbox', 'BTC-USD', '1m')
    forming_candle = store.candles.get_current_candle('Sandbox', 'BTC-USD', '5m')
    assert forming_candle[0] == candles_to_add[0][0]
    assert forming_candle[1] == candles_to_add[0][1]
    assert forming_candle[2] == candles_to_add[3][2]

    # add the rest of 1m candles
    store.candles.batch_add_candle(candles_to_add[4:], 'Sandbox', 'BTC-USD', '1m')
    # add 5m candles
    store.candles.batch_add_candle(candles_to_add[0:5], 'Sandbox', 'BTC-USD', '5m')
    store.candles.batch_add_candle(candles_to_add[5:10], 'Sandbox', 'BTC-USD', '5m')

    forming_candle = store.candles.get_current_candle('Sandbox', 'BTC-USD', '5m')
    assert forming_candle[0] == candles_to_add[10][0]
    assert forming_candle[1] == candles_to_add[10][1]
    assert forming_candle[2] == candles_to_add[12][2]


def test_can_update_candle():
    set_up()

    np.testing.assert_equal(store.candles.get_candles('Sandbox', 'BTC-USD', '1m'), np.zeros((0, 6)))

    # add it
    c1 = fake_candle()
    store.candles.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(store.candles.get_current_candle('Sandbox', 'BTC-USD', '1m'), c1)

    # now update it with another candle which has the same timestamp
    c2 = c1.copy()
    c2[1] = 1000
    store.candles.add_candle(c2, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(store.candles.get_current_candle('Sandbox', 'BTC-USD', '1m'), c2)
    assert len(store.candles.get_candles('Sandbox', 'BTC-USD', '1m')) == 1


def test_can_update_previous_candle():
    set_up()

    # add 1th candle
    c1 = fake_candle()
    store.candles.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')

    # add 2nd candle
    c2 = fake_candle()
    store.candles.add_candle(c2, 'Sandbox', 'BTC-USD', '1m')

    # add 3rd candle
    c3 = fake_candle()
    store.candles.add_candle(c3, 'Sandbox', 'BTC-USD', '1m')

    # create a new candle from c2 and update its closing price
    new_c2 = c2.copy()
    new_c2[2] = 50

    # assert that the 2nd candle is not updated yet
    assert store.candles.get_candles('Sandbox', 'BTC-USD', '1m')[-2][2] != c3[2]

    # update the 2nd candle
    store.candles.add_candle(new_c2, 'Sandbox', 'BTC-USD', '1m')

    # assert that the 2nd candle is updated now
    assert store.candles.get_candles('Sandbox', 'BTC-USD', '1m')[-2][2] == new_c2[2]
