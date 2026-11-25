"""Completed-candle reads at deterministic strategy and wall-clock boundaries."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

import jesse.helpers as jh
from jesse.enums import exchanges
from jesse.exceptions import RouteNotFound
from jesse.libs import DynamicNumpyArray
from jesse.routes import router
from jesse.services import candle_service
from jesse.store import store
from jesse.testing_utils import set_up


EXCHANGE = exchanges.SANDBOX
SYMBOL = 'BTC-USDT'
# Use a UTC midnight so every tested timeframe is aligned to its clock bucket.
BOUNDARY = 1_704_153_600_000


@pytest.fixture(params=['legacy-backtest', 'timestamp-backtest', 'live'])
def stored(request, monkeypatch):
    set_up()
    router.initiate([{'exchange': EXCHANGE, 'symbol': SYMBOL, 'timeframe': '30m', 'strategy': 'TestVanillaStrategy'}])
    store.reset()
    monkeypatch.setattr(jh, 'is_live', lambda: request.param == 'live')
    store.candles.uses_timestamp_buckets = request.param == 'timestamp-backtest'
    for timeframe in ('1m', '30m', '4h', '1D'):
        duration = jh.timeframe_to_one_minutes(timeframe) * 60_000
        array = DynamicNumpyArray((10, 6))
        for i, timestamp in enumerate((BOUNDARY - duration, BOUNDARY, BOUNDARY + duration)):
            array.append(np.array([timestamp, 100 + i, 101 + i, 102 + i, 99 + i, 10], dtype=float))
        store.candles.storage[f'{EXCHANGE}-{SYMBOL}-{timeframe}'] = array
    yield
    store.reset()


@pytest.mark.parametrize('timeframe', ['1m', '30m', '4h', '1D'])
@pytest.mark.parametrize('boundary_offset, count', [(-1, 0), (0, 1), (1, 1), (2, 2)])
def test_closed_candles_include_a_bar_only_after_its_close(stored, monkeypatch, timeframe, boundary_offset, count):
    duration = jh.timeframe_to_one_minutes(timeframe) * 60_000
    # -1 ms before the first close; at it; -1 ms before the next; at the next.
    times = {-1: BOUNDARY - 1, 0: BOUNDARY, 1: BOUNDARY + duration - 1, 2: BOUNDARY + duration}
    now = times[boundary_offset]
    monkeypatch.setattr(jh, 'now', lambda: now)
    source = store.candles.get_storage(EXCHANGE, SYMBOL, timeframe)
    before = source[:].copy()

    result = candle_service.get_candles(EXCHANGE, SYMBOL, timeframe)

    np.testing.assert_array_equal(result, before[:count])
    np.testing.assert_array_equal(source[:], before)


def test_delayed_strategy_uses_its_execution_boundary(stored, monkeypatch):
    duration = 4 * 60 * 60_000
    monkeypatch.setattr(jh, 'now', lambda: BOUNDARY + 5 * duration)
    store.candles.execution_cutoff = BOUNDARY + 30 * 60_000

    result = candle_service.get_candles(EXCHANGE, SYMBOL, '4h')

    assert result[:, 0].tolist() == [BOUNDARY - duration]
    # Data ingestion threads must retain their own current-time view.
    with ThreadPoolExecutor(max_workers=1) as executor:
        background = executor.submit(candle_service.get_candles, EXCHANGE, SYMBOL, '4h').result()
    assert len(background) == 3


def test_all_stored_candles_can_be_closed(stored, monkeypatch):
    monkeypatch.setattr(jh, 'now', lambda: BOUNDARY + 24 * 60 * 60_000)
    source = store.candles.get_storage(EXCHANGE, SYMBOL, '4h')
    np.testing.assert_array_equal(candle_service.get_candles(EXCHANGE, SYMBOL, '4h'), source[:])


def test_empty_storage_returns_an_empty_candle_array(stored, monkeypatch):
    monkeypatch.setattr(jh, 'now', lambda: BOUNDARY)
    store.candles.storage[f'{EXCHANGE}-{SYMBOL}-4h'] = DynamicNumpyArray((10, 6))
    assert candle_service.get_candles(EXCHANGE, SYMBOL, '4h').shape == (0, 6)


def test_missing_route_raises_the_existing_route_error(stored):
    with pytest.raises(RouteNotFound):
        candle_service.get_candles(EXCHANGE, 'MISSING-USDT', '4h')


def test_gaps_in_stored_history_are_not_filled(stored, monkeypatch):
    duration = 4 * 60 * 60_000
    monkeypatch.setattr(jh, 'now', lambda: BOUNDARY + 2 * duration)
    source = store.candles.get_storage(EXCHANGE, SYMBOL, '4h')[:].copy()
    sparse = DynamicNumpyArray((10, 6))
    sparse.append(source[0])
    sparse.append(source[2])
    store.candles.storage[f'{EXCHANGE}-{SYMBOL}-4h'] = sparse
    np.testing.assert_array_equal(candle_service.get_candles(EXCHANGE, SYMBOL, '4h'), source[[0, 2]])


def test_zero_execution_boundary_does_not_fall_back_to_wall_time(stored, monkeypatch):
    monkeypatch.setattr(jh, 'now', lambda: BOUNDARY + 24 * 60 * 60_000)
    store.candles.execution_cutoff = 0
    assert candle_service.get_candles(EXCHANGE, SYMBOL, '4h').shape == (0, 6)


def test_sparse_current_read_excludes_minutes_after_a_delayed_boundary(stored, monkeypatch):
    store.candles.uses_timestamp_buckets = True
    store.candles.execution_cutoff = BOUNDARY + 30 * 60_000
    monkeypatch.setattr(jh, 'now', lambda: BOUNDARY + 50 * 60_000)
    minutes = DynamicNumpyArray((10, 6))
    for row in (
        [BOUNDARY, 10, 10, 11, 9, 1],
        [BOUNDARY + 20 * 60_000, 10, 20, 21, 9, 2],
        [BOUNDARY + 40 * 60_000, 20, 99, 100, 19, 3],
    ):
        minutes.append(np.array(row, dtype=float))
    store.candles.storage[f'{EXCHANGE}-{SYMBOL}-1m'] = minutes
    before = store.candles.get_storage(EXCHANGE, SYMBOL, '4h')[:].copy()

    # Sparse live storage may already include a minute that arrived after the
    # decision cutoff. Current reads must rebuild the forming bar causally.
    np.testing.assert_array_equal(
        candle_service.get_current_candle(EXCHANGE, SYMBOL, '4h'),
        np.array([BOUNDARY, 10, 20, 21, 9, 3]),
    )
    np.testing.assert_array_equal(candle_service.get_candles(EXCHANGE, SYMBOL, '4h'), before[:1])
    np.testing.assert_array_equal(store.candles.get_storage(EXCHANGE, SYMBOL, '4h')[:], before)
