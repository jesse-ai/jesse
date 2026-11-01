from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

import jesse.helpers as jh
from jesse.enums import exchanges
from jesse.libs import DynamicNumpyArray
from jesse.routes import router
from jesse.services import candle_service
from jesse.store import store
from jesse.testing_utils import set_up


MINUTE = 60_000
BOUNDARY = 1_700_000_100_000
EXCHANGE = exchanges.SANDBOX
SYMBOL = 'BTC-USDT'


def _candle(open_time: int) -> np.ndarray:
    return np.array([open_time, 100, 101, 102, 99, 10], dtype=float)


def _in_another_thread(work):
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(work).result()


@pytest.fixture
def stored(monkeypatch):
    set_up()
    router.initiate([{'exchange': EXCHANGE, 'symbol': SYMBOL, 'timeframe': '1m', 'strategy': 'TestVanillaStrategy'}])
    store.reset()
    monkeypatch.setattr(jh, 'is_live', lambda: True)
    for timeframe, open_times in (
        ('1m', (BOUNDARY - 2 * MINUTE, BOUNDARY - MINUTE, BOUNDARY)),
        ('5m', (BOUNDARY - 5 * MINUTE, BOUNDARY)),
    ):
        storage = DynamicNumpyArray((100, 6))
        for open_time in open_times:
            storage.append(_candle(open_time))
        store.candles.storage[f'{EXCHANGE}-{SYMBOL}-{timeframe}'] = storage
    yield
    store.candles.execution_cutoff = None


def test_reads_stop_before_a_candle_that_opened_at_the_boundary(stored):
    store.candles.execution_cutoff = BOUNDARY

    assert candle_service.get_candles(EXCHANGE, SYMBOL, '1m')[:, 0].tolist() == [BOUNDARY - 2 * MINUTE, BOUNDARY - MINUTE]
    assert candle_service.get_current_candle(EXCHANGE, SYMBOL, '1m')[0] == BOUNDARY - MINUTE
    assert candle_service.get_candles(EXCHANGE, SYMBOL, '5m')[:, 0].tolist() == [BOUNDARY - 5 * MINUTE]
    assert candle_service.get_current_candle(EXCHANGE, SYMBOL, '5m')[0] == BOUNDARY - 5 * MINUTE


def test_a_bigger_candle_still_forming_at_the_boundary_stays_visible(stored):
    store.candles.execution_cutoff = BOUNDARY + MINUTE

    assert candle_service.get_current_candle(EXCHANGE, SYMBOL, '5m')[0] == BOUNDARY
    assert candle_service.get_current_candle(EXCHANGE, SYMBOL, '1m')[0] == BOUNDARY


def test_without_a_cutoff_reads_include_the_latest_candle(stored):
    assert candle_service.get_current_candle(EXCHANGE, SYMBOL, '1m')[0] == BOUNDARY
    assert candle_service.get_candles(EXCHANGE, SYMBOL, '5m')[-1][0] == BOUNDARY


def test_a_cutoff_before_every_candle_reads_nothing(stored):
    store.candles.execution_cutoff = BOUNDARY - 10 * MINUTE

    assert len(candle_service.get_candles(EXCHANGE, SYMBOL, '1m')) == 0
    assert len(candle_service.get_current_candle(EXCHANGE, SYMBOL, '1m')) == 0


def test_only_the_thread_running_strategies_has_a_cutoff(stored):
    store.candles.execution_cutoff = BOUNDARY

    assert _in_another_thread(lambda: store.candles.execution_cutoff) is None
    assert _in_another_thread(lambda: candle_service.get_current_candle(EXCHANGE, SYMBOL, '1m')[0]) == BOUNDARY
    assert _in_another_thread(lambda: candle_service.get_candles(EXCHANGE, SYMBOL, '5m')[-1][0]) == BOUNDARY
    assert candle_service.get_current_candle(EXCHANGE, SYMBOL, '1m')[0] == BOUNDARY - MINUTE


def test_a_trade_during_a_late_run_goes_into_the_forming_candle(stored, monkeypatch):
    store.candles.initiated_pairs[f'{EXCHANGE}-{SYMBOL}'] = True
    monkeypatch.setattr(jh, 'now', lambda *args, **kwargs: BOUNDARY + 1000)
    monkeypatch.setattr(candle_service, '_store_or_update_candle_into_db', lambda *args: None)
    monkeypatch.setattr(candle_service, '_update_position_current_price', lambda *args: None)
    store.candles.execution_cutoff = BOUNDARY

    _in_another_thread(lambda: candle_service.add_candle_from_trade({'price': 105, 'volume': 3}, EXCHANGE, SYMBOL))

    store.candles.execution_cutoff = None
    closed, forming = candle_service.get_candles(EXCHANGE, SYMBOL, '1m')[-2:]
    assert closed.tolist() == _candle(BOUNDARY - MINUTE).tolist()
    assert forming.tolist() == [BOUNDARY, 100, 105, 105, 99, 13]
