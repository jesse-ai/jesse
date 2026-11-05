import arrow
import numpy as np
import pytest
from types import SimpleNamespace

from jesse.config import config, reset_config
from jesse.factories import fake_candle, range_candles
from jesse.services import candle_service
from jesse.store import store


def set_up():
    reset_config()
    from jesse.routes import router
    router.set_routes([
        {'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '1m', 'strategy': 'Test01'}
    ])
    router.set_data_routes([{'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '5m'}])
    config['app']['considering_timeframes'] = ['1m', '5m']
    config['app']['considering_symbols'] = ['BTC-USD']
    config['app']['considering_exchanges'] = ['Sandbox']
    store.reset()
    store.candles.init_storage()


def test_batch_add_candles():
    set_up()

    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '1m')) == 0

    # create 100 candles
    candles_to_add = range_candles(100)
    assert len(candles_to_add) == 100

    candle_service.batch_add_candle(candles_to_add, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m'), candles_to_add)


def test_can_add_new_candle():
    set_up()

    np.testing.assert_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m'), np.zeros((0, 6)))

    c1 = fake_candle()
    candle_service.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m')[0], c1)
    # try to add duplicate
    candle_service.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')
    # assert to make sure it's the same
    np.testing.assert_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m')[0], c1)

    c2 = fake_candle()
    candle_service.add_candle(c2, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m'), np.array([c1, c2]))


def test_get_candles_including_forming():
    set_up()

    candles_to_add = range_candles(14)
    candle_service.batch_add_candle(candles_to_add, 'Sandbox', 'BTC-USD', '1m')
    candle_service.add_candle(
        candle_service.generate_candle_from_one_minutes(
            '5m', candles_to_add[0:5], False
        ),
        'Sandbox', 'BTC-USD', '5m'
    )
    candle_service.add_candle(
        candle_service.generate_candle_from_one_minutes(
            '5m', candles_to_add[5:10], False
        ),
        'Sandbox', 'BTC-USD', '5m'
    )

    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '5m')) == 3
    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '1m')) == 14

    candles = candle_service.get_candles('Sandbox', 'BTC-USD', '5m')
    assert candles[0][0] == candles_to_add[0][0]
    assert candles[-1][2] == candles_to_add[13][2]
    assert candles[-1][0] == candles_to_add[10][0]

    # add third one while still a forming candle. Now since
    # we already have forming, get_candles() must not
    # append another forming candle to the end.
    candle_service.add_candle(
        candle_service.generate_candle_from_one_minutes(
            '5m', candles_to_add[10:14], True
        ),
        'Sandbox', 'BTC-USD', '5m'
    )

    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '5m')) == 3
    assert candles[-1][2] == candles_to_add[13][2]
    assert candles[-1][0] == candles_to_add[10][0]


def test_get_forming_candle():
    set_up()

    candles_to_add = range_candles(13)
    candle_service.batch_add_candle(candles_to_add[0:4], 'Sandbox', 'BTC-USD', '1m')
    forming_candle = candle_service.get_current_candle('Sandbox', 'BTC-USD', '5m')
    assert forming_candle[0] == candles_to_add[0][0]
    assert forming_candle[1] == candles_to_add[0][1]
    assert forming_candle[2] == candles_to_add[3][2]

    # add the rest of 1m candles
    candle_service.batch_add_candle(candles_to_add[4:], 'Sandbox', 'BTC-USD', '1m')
    # add 5m candles
    candle_service.batch_add_candle(candles_to_add[0:5], 'Sandbox', 'BTC-USD', '5m')
    candle_service.batch_add_candle(candles_to_add[5:10], 'Sandbox', 'BTC-USD', '5m')

    forming_candle = candle_service.get_current_candle('Sandbox', 'BTC-USD', '5m')
    assert forming_candle[0] == candles_to_add[10][0]
    assert forming_candle[1] == candles_to_add[10][1]
    assert forming_candle[2] == candles_to_add[12][2]


def test_can_update_candle():
    set_up()

    np.testing.assert_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m'), np.zeros((0, 6)))

    # add it
    c1 = fake_candle()
    candle_service.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(candle_service.get_current_candle('Sandbox', 'BTC-USD', '1m'), c1)

    # now update it with another candle which has the same timestamp
    c2 = c1.copy()
    c2[1] = 1000
    candle_service.add_candle(c2, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_equal(candle_service.get_current_candle('Sandbox', 'BTC-USD', '1m'), c2)
    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '1m')) == 1


def test_can_update_previous_candle():
    set_up()

    # add 1th candle
    c1 = fake_candle()
    candle_service.add_candle(c1, 'Sandbox', 'BTC-USD', '1m')

    # add 2nd candle
    c2 = fake_candle()
    candle_service.add_candle(c2, 'Sandbox', 'BTC-USD', '1m')

    # add 3rd candle
    c3 = fake_candle()
    candle_service.add_candle(c3, 'Sandbox', 'BTC-USD', '1m')

    # create a new candle from c2 and update its closing price
    new_c2 = c2.copy()
    new_c2[2] = 50

    # assert that the 2nd candle is not updated yet
    assert candle_service.get_candles('Sandbox', 'BTC-USD', '1m')[-2][2] != c3[2]

    # update the 2nd candle
    candle_service.add_candle(new_c2, 'Sandbox', 'BTC-USD', '1m')

    # assert that the 2nd candle is updated now
    assert candle_service.get_candles('Sandbox', 'BTC-USD', '1m')[-2][2] == new_c2[2]


def test_warmup_injection_generates_exact_5m_15m_and_1h_candles():
    set_up()
    config['app']['considering_timeframes'] = ['1m', '5m', '15m', '1h']
    store.reset()
    store.candles.init_storage(bucket_size=120)

    # Use exactly one aligned hour of steadily increasing OHLCV data so every
    # generated timeframe has complete buckets with easy-to-audit values.
    start = 1_700_000_000_000
    start -= start % 3_600_000
    candles = np.array([
        [start + i * 60_000, i + 1, i + 2, i + 3, i, 1]
        for i in range(60)
    ], dtype=np.float64)

    candle_service.inject_warmup_candles_to_store(candles, 'Sandbox', 'BTC-USD')

    # Verify the first aggregate's full [timestamp, open, close, high, low, volume]
    # payload, not only the number of generated candles.
    np.testing.assert_array_equal(
        candle_service.get_candles('Sandbox', 'BTC-USD', '5m')[0],
        np.array([start, 1, 6, 7, 0, 5], dtype=np.float64),
    )
    np.testing.assert_array_equal(
        candle_service.get_candles('Sandbox', 'BTC-USD', '15m')[0],
        np.array([start, 1, 16, 17, 0, 15], dtype=np.float64),
    )
    np.testing.assert_array_equal(
        candle_service.get_candles('Sandbox', 'BTC-USD', '1h')[0],
        np.array([start, 1, 61, 62, 0, 60], dtype=np.float64),
    )

    # A full hour must produce only complete buckets for each target timeframe.
    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '5m')) == 12
    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '15m')) == 4
    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '1h')) == 1


def test_multiple_symbols_and_data_route_timeframes_remain_isolated():
    reset_config()
    from jesse.routes import router

    # The trading route and data route intentionally use different symbols and
    # timeframes to catch storage-key leakage between route types.
    router.set_routes([
        {'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '5m', 'strategy': 'Test01'},
    ])
    router.set_data_routes([
        {'exchange': 'Sandbox', 'symbol': 'ETH-USD', 'timeframe': '15m'},
    ])
    config['app']['considering_timeframes'] = ['1m', '5m', '15m']
    store.reset()
    store.candles.init_storage(bucket_size=30)
    btc = range_candles(15)
    eth = range_candles(15).copy()

    # Keep ETH in a distinct price band so cross-symbol contamination is visible.
    eth[:, 1:] += 1_000

    # Add each timeframe explicitly; this test targets storage isolation rather
    # than the automatic generation behavior covered by the warmup test above.
    candle_service.batch_add_candle(btc, 'Sandbox', 'BTC-USD', '1m', with_generation=False)
    candle_service.batch_add_candle(eth, 'Sandbox', 'ETH-USD', '1m', with_generation=False)
    candle_service.batch_add_candle(
        candle_service._get_generated_candles('5m', btc),
        'Sandbox', 'BTC-USD', '5m', with_generation=False,
    )
    candle_service.batch_add_candle(
        candle_service._get_generated_candles('15m', eth),
        'Sandbox', 'ETH-USD', '15m', with_generation=False,
    )

    np.testing.assert_array_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m'), btc)
    np.testing.assert_array_equal(candle_service.get_candles('Sandbox', 'ETH-USD', '1m'), eth)
    assert len(candle_service.get_candles('Sandbox', 'BTC-USD', '5m')) == 3
    assert len(candle_service.get_candles('Sandbox', 'ETH-USD', '15m')) == 1
    assert candle_service.get_candles('Sandbox', 'BTC-USD', '5m')[-1][2] < 1_000
    assert candle_service.get_candles('Sandbox', 'ETH-USD', '15m')[-1][2] > 1_000


def test_live_trade_updates_candle_position_and_database(monkeypatch):
    set_up()
    config['app']['considering_timeframes'] = ['1m']
    config['env']['data']['generate_candles_from_1m'] = True
    store.reset()
    store.candles.init_storage()

    # Seed an active one-minute candle; a trade 30 seconds later must update this
    # candle in place instead of opening the next minute.
    start = 1_700_000_040_000
    initial = np.array([start, 10, 11, 12, 9, 5], dtype=np.float64)
    store.candles.get_storage('Sandbox', 'BTC-USD', '1m').append(initial)
    store.candles.initiated_pairs['Sandbox-BTC-USD'] = True
    position = SimpleNamespace(current_price=0)
    writes = []
    exchange = SimpleNamespace(vars={
        'precisions': {'BTC-USD': {'price_precision': 2}},
    })

    # Exercise the live path while replacing external state with observable fakes.
    monkeypatch.setattr(candle_service.jh, 'is_live', lambda: True)
    monkeypatch.setattr(candle_service.jh, 'now', lambda: start + 30_000)
    monkeypatch.setattr(store.positions, 'get_position', lambda exchange, symbol: position)
    monkeypatch.setattr(store.exchanges, 'get_exchange', lambda name: exchange)
    monkeypatch.setattr(
        candle_service.candle_repository,
        'store_candle_into_db',
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    updated = candle_service.add_candle_from_trade(
        {'price': 13.126, 'volume': 2.5}, 'Sandbox', 'BTC-USD',
    )

    # The trade raises close/high and accumulates volume while preserving open/low.
    np.testing.assert_array_equal(
        updated,
        np.array([start, 10, 13.126, 13.126, 9, 7.5], dtype=np.float64),
    )
    np.testing.assert_array_equal(
        candle_service.get_current_candle('Sandbox', 'BTC-USD', '1m'), updated,
    )

    # Position prices obey exchange precision, while persistence receives the
    # unrounded candle once with replacement semantics.
    assert position.current_price == 13.13
    assert len(writes) == 1
    assert writes[0][0][0:3] == ('Sandbox', 'BTC-USD', '1m')
    assert writes[0][1] == {'on_conflict': 'replace'}


def test_live_trade_updates_every_route_timeframe_of_its_symbol(monkeypatch):
    set_up()
    config['app']['considering_timeframes'] = ['1m', '15m', '1h']
    config['env']['data']['generate_candles_from_1m'] = False
    store.reset()
    store.candles.init_storage()

    start = 1_699_999_200_000
    for timeframe in ('15m', '1h'):
        store.candles.get_storage('Sandbox', 'BTC-USD', timeframe).append(
            np.array([start, 10, 11, 12, 9, 5], dtype=np.float64)
        )
    store.candles.initiated_pairs['Sandbox-BTC-USD'] = True
    position = SimpleNamespace(current_price=0)
    exchange = SimpleNamespace(vars={'precisions': {'BTC-USD': {'price_precision': 2}}})

    # Another symbol's route comes first, and BTC-USD has a trading and a data route.
    routes = [
        {'exchange': 'Sandbox', 'symbol': 'ETH-USD', 'timeframe': '5m'},
        {'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '15m'},
        {'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '1h'},
    ]
    monkeypatch.setattr(type(candle_service.router), 'all_formatted_routes', property(lambda self: routes))
    monkeypatch.setattr(candle_service.jh, 'is_live', lambda: True)
    monkeypatch.setattr(candle_service.jh, 'now', lambda: start + 60_000)
    monkeypatch.setattr(store.positions, 'get_position', lambda exchange, symbol: position)
    monkeypatch.setattr(store.exchanges, 'get_exchange', lambda name: exchange)
    monkeypatch.setattr(candle_service.candle_repository, 'store_candle_into_db', lambda *args, **kwargs: None)

    updated = candle_service.add_candle_from_trade({'price': 13, 'volume': 2}, 'Sandbox', 'BTC-USD')

    expected = np.array([start, 10, 13, 13, 9, 7], dtype=np.float64)
    np.testing.assert_array_equal(updated, expected)
    for timeframe in ('15m', '1h'):
        np.testing.assert_array_equal(candle_service.get_current_candle('Sandbox', 'BTC-USD', timeframe), expected)


def _live_one_minute_trades(monkeypatch, now, timeframes=('1m',)):
    set_up()
    config['app']['considering_timeframes'] = list(timeframes)
    config['env']['data']['generate_candles_from_1m'] = True
    store.reset()
    store.candles.init_storage()
    store.candles.initiated_pairs['Sandbox-BTC-USD'] = True
    exchange = SimpleNamespace(vars={'precisions': {'BTC-USD': {'price_precision': 2}}})
    monkeypatch.setattr(candle_service.jh, 'is_live', lambda: True)
    monkeypatch.setattr(candle_service.jh, 'now', lambda: now)
    monkeypatch.setattr(store.positions, 'get_position', lambda exchange, symbol: SimpleNamespace(current_price=0))
    monkeypatch.setattr(store.exchanges, 'get_exchange', lambda name: exchange)
    monkeypatch.setattr(candle_service.candle_repository, 'store_candle_into_db', lambda *args, **kwargs: None)
    return store.candles.get_storage('Sandbox', 'BTC-USD', '1m')


def test_late_trade_updates_the_candle_it_belongs_to(monkeypatch):
    start = 1_700_000_040_000
    arr = _live_one_minute_trades(monkeypatch, now=start + 60_000 + 2_000)
    arr.append(np.array([start, 10, 11, 12, 9, 5], dtype=np.float64))

    # Traded one second before the minute closed, received two seconds after it.
    result = candle_service.add_candle_from_trade(
        {'price': 12.5, 'volume': 2, 'timestamp': start + 59_000}, 'Sandbox', 'BTC-USD',
    )

    assert result is None
    np.testing.assert_array_equal(arr[-2], np.array([start, 10, 12.5, 12.5, 9, 7]))
    # the new minute stays an untouched placeholder
    np.testing.assert_array_equal(arr[-1], np.array([start + 60_000, 11, 11, 11, 11, 0]))


# On a whole minute of the clock, and of the 5m clock too.
BOUNDARY = 1_700_000_100_000
CLOSED_1M = np.array([BOUNDARY - 60_000, 10, 11, 12, 9, 5], dtype=np.float64)
CLOSED_5M = np.array([BOUNDARY - 300_000, 8, 11, 12, 7, 50], dtype=np.float64)


def _closed_candles_at_the_boundary(monkeypatch, now):
    arr = _live_one_minute_trades(monkeypatch, now, timeframes=('1m', '5m'))
    arr.append(CLOSED_1M.copy())
    bigger = store.candles.get_storage('Sandbox', 'BTC-USD', '5m')
    bigger.append(CLOSED_5M.copy())
    return arr, bigger


def test_trades_in_the_first_second_of_a_minute_start_the_new_candle(monkeypatch):
    arr = _live_one_minute_trades(monkeypatch, now=BOUNDARY)
    arr.append(CLOSED_1M.copy())

    first = candle_service.add_candle_from_trade({'price': 13, 'volume': 1}, 'Sandbox', 'BTC-USD')
    second = candle_service.add_candle_from_trade({'price': 8, 'volume': 2}, 'Sandbox', 'BTC-USD')

    assert len(arr) == 2
    np.testing.assert_array_equal(first, np.array([BOUNDARY, 11, 13, 13, 11, 1]))
    np.testing.assert_array_equal(second, np.array([BOUNDARY, 11, 8, 13, 8, 3]))
    np.testing.assert_array_equal(arr[-1], second)
    np.testing.assert_array_equal(arr[-2], CLOSED_1M)


@pytest.mark.parametrize('offset_ms, candle_timestamp', [
    (-1, BOUNDARY - 60_000),
    (0, BOUNDARY),
    (300, BOUNDARY),
    (999, BOUNDARY),
    (1_000, BOUNDARY),
])
def test_the_clock_decides_the_candle_of_a_trade_to_the_millisecond(monkeypatch, offset_ms, candle_timestamp):
    # jh.now() itself must run here, as whole seconds are what the first second comes from.
    real_now = candle_service.jh.now
    arr = _live_one_minute_trades(monkeypatch, now=None)
    arr.append(CLOSED_1M.copy())
    monkeypatch.setattr(candle_service.jh, 'now', real_now)
    monkeypatch.setattr(candle_service.jh.arrow, 'utcnow', lambda: arrow.get((BOUNDARY + offset_ms) / 1000))

    updated = candle_service.add_candle_from_trade({'price': 13, 'volume': 1}, 'Sandbox', 'BTC-USD')

    assert updated[0] == candle_timestamp
    assert arr[-1][0] == candle_timestamp


def test_first_second_trade_with_its_own_time_goes_to_the_new_candle(monkeypatch):
    arr = _live_one_minute_trades(monkeypatch, now=BOUNDARY)
    arr.append(CLOSED_1M.copy())

    updated = candle_service.add_candle_from_trade(
        {'price': 13, 'volume': 1, 'timestamp': BOUNDARY + 300}, 'Sandbox', 'BTC-USD',
    )

    np.testing.assert_array_equal(updated, np.array([BOUNDARY, 11, 13, 13, 11, 1]))
    np.testing.assert_array_equal(arr[-2], CLOSED_1M)


def test_late_trade_received_in_the_first_second_stays_in_the_candle_it_belongs_to(monkeypatch):
    arr = _live_one_minute_trades(monkeypatch, now=BOUNDARY)
    arr.append(CLOSED_1M.copy())

    result = candle_service.add_candle_from_trade(
        {'price': 12.5, 'volume': 2, 'timestamp': BOUNDARY - 100}, 'Sandbox', 'BTC-USD',
    )

    assert result is None
    np.testing.assert_array_equal(arr[-2], np.array([BOUNDARY - 60_000, 10, 12.5, 12.5, 9, 7]))
    np.testing.assert_array_equal(arr[-1], np.array([BOUNDARY, 11, 11, 11, 11, 0]))


def test_first_second_trade_starts_the_bigger_candle_that_opened_with_it(monkeypatch):
    arr, bigger = _closed_candles_at_the_boundary(monkeypatch, now=BOUNDARY)

    candle_service.add_candle_from_trade({'price': 13, 'volume': 1}, 'Sandbox', 'BTC-USD')

    np.testing.assert_array_equal(arr[-1], np.array([BOUNDARY, 11, 13, 13, 11, 1]))
    np.testing.assert_array_equal(bigger[-1], np.array([BOUNDARY, 11, 13, 13, 11, 1]))
    np.testing.assert_array_equal(bigger[-2], CLOSED_5M)


def test_on_time_run_does_not_see_the_candles_a_first_second_trade_started(monkeypatch):
    _closed_candles_at_the_boundary(monkeypatch, now=BOUNDARY)
    candle_service.add_candle_from_trade({'price': 13, 'volume': 1}, 'Sandbox', 'BTC-USD')

    store.candles.execution_cutoff = BOUNDARY
    try:
        np.testing.assert_array_equal(candle_service.get_current_candle('Sandbox', 'BTC-USD', '1m'), CLOSED_1M)
        np.testing.assert_array_equal(candle_service.get_current_candle('Sandbox', 'BTC-USD', '5m'), CLOSED_5M)
        np.testing.assert_array_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '1m')[-1], CLOSED_1M)
        np.testing.assert_array_equal(candle_service.get_candles('Sandbox', 'BTC-USD', '5m')[-1], CLOSED_5M)
    finally:
        store.candles.execution_cutoff = None


def test_first_second_trade_starts_only_the_timeframes_that_opened(monkeypatch):
    set_up()
    config['app']['considering_timeframes'] = ['1m', '15m', '1h']
    config['env']['data']['generate_candles_from_1m'] = False
    store.reset()
    store.candles.init_storage()
    store.candles.initiated_pairs['Sandbox-BTC-USD'] = True

    start = 1_699_999_200_000
    now = start + 900_000
    closed = np.array([start, 10, 11, 12, 9, 5], dtype=np.float64)
    for timeframe in ('15m', '1h'):
        store.candles.get_storage('Sandbox', 'BTC-USD', timeframe).append(closed.copy())
    exchange = SimpleNamespace(vars={'precisions': {'BTC-USD': {'price_precision': 2}}})
    routes = [
        {'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '15m'},
        {'exchange': 'Sandbox', 'symbol': 'BTC-USD', 'timeframe': '1h'},
    ]
    monkeypatch.setattr(type(candle_service.router), 'all_formatted_routes', property(lambda self: routes))
    monkeypatch.setattr(candle_service.jh, 'is_live', lambda: True)
    monkeypatch.setattr(candle_service.jh, 'now', lambda: now)
    monkeypatch.setattr(store.positions, 'get_position', lambda exchange, symbol: SimpleNamespace(current_price=0))
    monkeypatch.setattr(store.exchanges, 'get_exchange', lambda name: exchange)
    monkeypatch.setattr(candle_service.candle_repository, 'store_candle_into_db', lambda *args, **kwargs: None)

    candle_service.add_candle_from_trade({'price': 13, 'volume': 2}, 'Sandbox', 'BTC-USD')

    fifteen_minutes = store.candles.get_storage('Sandbox', 'BTC-USD', '15m')
    np.testing.assert_array_equal(fifteen_minutes[-2], closed)
    np.testing.assert_array_equal(fifteen_minutes[-1], np.array([now, 11, 13, 13, 11, 2]))
    np.testing.assert_array_equal(
        store.candles.get_storage('Sandbox', 'BTC-USD', '1h')[-1], np.array([start, 10, 13, 13, 9, 7]),
    )


class _ManualTimeloop:
    """Stands in for Timeloop, so that a test decides when the registered job ticks."""

    def job(self, interval):
        def register(job):
            self.tick = job
            return job
        return register

    def start(self):
        pass


def test_candle_generator_keeps_the_candles_a_first_second_trade_started(monkeypatch):
    arr, bigger = _closed_candles_at_the_boundary(monkeypatch, now=BOUNDARY)
    candle_service.add_candle_from_trade({'price': 13, 'volume': 1}, 'Sandbox', 'BTC-USD')
    started = np.array([BOUNDARY, 11, 13, 13, 11, 1])

    timer = _ManualTimeloop()
    monkeypatch.setattr(candle_service, 'Timeloop', lambda: timer)
    monkeypatch.setattr(candle_service.jh, 'now', lambda: BOUNDARY + 1_000)
    store.candles.are_all_initiated = True
    candle_service.generate_new_candles_loop()
    timer.tick()

    np.testing.assert_array_equal(arr[-1], started)
    np.testing.assert_array_equal(bigger[-1], started)


def test_candle_generator_still_fills_a_minute_without_trades(monkeypatch):
    arr, bigger = _closed_candles_at_the_boundary(monkeypatch, now=BOUNDARY + 1_000)

    timer = _ManualTimeloop()
    monkeypatch.setattr(candle_service, 'Timeloop', lambda: timer)
    store.candles.are_all_initiated = True
    candle_service.generate_new_candles_loop()
    timer.tick()

    np.testing.assert_array_equal(arr[-1], np.array([BOUNDARY, 11, 11, 11, 11, 0]))
    np.testing.assert_array_equal(bigger[-1], np.array([BOUNDARY, 11, 11, 11, 11, 0]))


def test_candle_from_a_stream_still_waits_out_its_opening_second(monkeypatch):
    arr = _live_one_minute_trades(monkeypatch, now=BOUNDARY)
    arr.append(CLOSED_1M.copy())
    streamed = np.array([BOUNDARY, 11, 12, 12, 11, 1], dtype=np.float64)

    candle_service.add_candle(streamed, 'Sandbox', 'BTC-USD', '1m')
    assert len(arr) == 1
    np.testing.assert_array_equal(arr[-1], CLOSED_1M)

    monkeypatch.setattr(candle_service.jh, 'now', lambda: BOUNDARY + 1_000)
    candle_service.add_candle(streamed, 'Sandbox', 'BTC-USD', '1m')
    np.testing.assert_array_equal(arr[-1], streamed)
