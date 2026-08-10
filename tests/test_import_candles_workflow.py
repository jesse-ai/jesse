import json

import arrow
import pytest

from jesse import exceptions
import jesse.modes.import_candles_mode as importer
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange


class _Expression:
    def __or__(self, other):
        return self


class _Field:
    def __init__(self, state):
        self.state = state

    def __eq__(self, other):
        return _Expression()

    def is_null(self):
        return _Expression()

    def between(self, start, end):
        self.state['range'] = (start, end)
        return _Expression()

    def asc(self):
        return self


def _candle_model(state):
    """Build a state-backed Peewee fake for page counts and backup-range reads."""
    class CountQuery:
        def where(self, *expressions):
            return self

        def count(self):
            start, _ = state['range']
            return state['counts'].get(start, 0)

    class TupleQuery:
        def where(self, *expressions):
            return self

        def order_by(self, *fields):
            return self

        def tuples(self):
            return list(state.get('tuples', []))

    class Candle:
        exchange = _Field(state)
        symbol = _Field(state)
        timeframe = _Field(state)
        timestamp = _Field(state)
        open = _Field(state)
        close = _Field(state)
        high = _Field(state)
        low = _Field(state)
        volume = _Field(state)

        @classmethod
        def select(cls, *fields):
            return TupleQuery() if fields else CountQuery()

    return Candle


class _FakeDriver(CandleExchange):
    """Return deterministic pages whose size exposes pagination and resume errors."""

    def __init__(self, fetches, count=720, starting_time=None):
        super().__init__('Fake Provider', count, 1000, None)
        self.fetches = fetches
        self.starting_time = starting_time

    def fetch(self, symbol, start_timestamp, timeframe='1m'):
        self.fetches.append((symbol, start_timestamp, timeframe))
        return [
            {
                'id': f'id-{start_timestamp + i * 60_000}',
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': start_timestamp + i * 60_000,
                'open': float(i + 1),
                'close': float(i + 2),
                'high': float(i + 3),
                'low': float(i),
                'volume': 4.0,
            }
            for i in range(self.count)
        ]

    def get_starting_time(self, symbol):
        return self.starting_time

    def get_available_symbols(self):
        return ['BTC-USDT']


def _configure_import(monkeypatch, state, driver, fixed_now):
    """Isolate an import run from the clock, database, Redis, and real providers."""
    from jesse.services.db import database

    database_events = []
    monkeypatch.setattr(importer, 'Candle', _candle_model(state))
    monkeypatch.setitem(importer.drivers, driver.name, lambda: driver)
    monkeypatch.setattr(importer.arrow, 'utcnow', lambda: fixed_now)
    monkeypatch.setattr(importer.jh, 'now_to_timestamp', lambda: fixed_now.int_timestamp * 1000 - 1)
    monkeypatch.setattr(importer.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(database, 'open_connection', lambda: database_events.append('open'))
    monkeypatch.setattr(database, 'close_connection', lambda: database_events.append('close'))
    return database_events


def test_import_paginates_with_exact_timestamps_and_closes_database(monkeypatch):
    fixed_now = arrow.get('2024-01-02T00:00:00Z')
    start = arrow.get('2024-01-01T00:00:00Z').int_timestamp * 1000
    state = {'range': None, 'counts': {}}
    fetches = []
    stored = []
    progress = []
    driver = _FakeDriver(fetches)
    database_events = _configure_import(monkeypatch, state, driver, fixed_now)

    def store(candles):
        stored.extend(candles)
        state['counts'][candles[0]['timestamp']] = len(candles)

    monkeypatch.setattr(importer, 'store_candles_list', store)
    monkeypatch.setattr(importer, '_store_import_progress', lambda *values: progress.append(values))

    result = importer.run(
        'client-1', driver.name, 'btc-usdt', '2024-01-01', running_via_dashboard=False,
    )

    assert fetches == [
        ('BTC-USDT', start, '1m'),
        ('BTC-USDT', start + 720 * 60_000, '1m'),
    ]
    assert len(stored) == 1440
    assert stored[0]['timestamp'] == start
    assert stored[-1]['timestamp'] == start + 1439 * 60_000
    assert progress and progress[0][0] == 'client-1'
    assert database_events == ['open', 'close']
    assert '1.0 days imported' in result


def test_import_resume_skips_complete_page_without_duplicate_fetch(monkeypatch):
    fixed_now = arrow.get('2024-01-02T00:00:00Z')
    start = arrow.get('2024-01-01T00:00:00Z').int_timestamp * 1000
    state = {'range': None, 'counts': {start: 720}}
    fetches = []
    stored = []
    driver = _FakeDriver(fetches)
    _configure_import(monkeypatch, state, driver, fixed_now)
    monkeypatch.setattr(importer, 'store_candles_list', lambda candles: stored.extend(candles))
    monkeypatch.setattr(importer, '_store_import_progress', lambda *values: None)

    result = importer.run(
        'client-2', driver.name, 'BTC-USDT', '2024-01-01', running_via_dashboard=False,
    )

    assert fetches == [('BTC-USDT', start + 720 * 60_000, '1m')]
    assert len(stored) == 720
    assert stored[0]['timestamp'] == start + 720 * 60_000
    assert '0.5 days imported' in result
    assert '0.5 days already existed' in result


def test_import_empty_response_raises_stable_error(monkeypatch):
    fixed_now = arrow.get('2024-01-02T00:00:00Z')
    state = {'range': None, 'counts': {}}
    driver = _FakeDriver([])
    _configure_import(monkeypatch, state, driver, fixed_now)
    monkeypatch.setattr(driver, 'fetch', lambda *args, **kwargs: [])

    with pytest.raises(exceptions.CandleNotFoundInExchange, match='No candles exists'):
        importer.run(
            'client-3', driver.name, 'BTC-USDT', '2024-01-01', running_via_dashboard=False,
        )


def test_dashboard_import_starts_and_stops_cancellation_checker(monkeypatch):
    fixed_now = arrow.get('2024-01-02T00:00:00Z')
    start = arrow.get('2024-01-01T00:00:00Z').int_timestamp * 1000
    state = {'range': None, 'counts': {start: 1440}}
    driver = _FakeDriver([], count=1440)
    _configure_import(monkeypatch, state, driver, fixed_now)
    events = []
    jobs = []
    published = []

    class FakeTimeloop:
        def job(self, interval):
            def decorate(fn):
                jobs.append(fn)
                return fn

            return decorate

        def start(self):
            events.append('checker-started')

        def stop(self):
            events.append('checker-stopped')

    monkeypatch.setattr(importer, 'Timeloop', FakeTimeloop)
    monkeypatch.setattr(importer, 'register_custom_exception_handler', lambda: events.append('handler'))
    monkeypatch.setattr(importer.store.app, 'set_session_id', lambda value: events.append(('session', value)))
    monkeypatch.setattr(importer, 'sync_publish', lambda channel, payload: published.append((channel, payload)))
    monkeypatch.setattr(importer, '_store_import_progress', lambda *values: None)
    monkeypatch.setattr(importer, 'is_process_active', lambda client_id: False)

    importer.run('client-4', driver.name, 'BTC-USDT', '2024-01-01')

    assert events == ['handler', ('session', 'client-4'), 'checker-started', 'checker-stopped']
    assert [channel for channel, _ in published] == ['alert']
    with pytest.raises(exceptions.Termination):
        jobs[0]()


def test_import_progress_is_persisted_and_redis_failures_are_non_fatal(monkeypatch):
    calls = []

    class FakeRedis:
        def set(self, key, value, ex=None):
            calls.append((key, json.loads(value), ex))

    monkeypatch.setattr(importer, 'sync_redis', FakeRedis())
    monkeypatch.setattr(importer, 'ENV_VALUES', {'APP_PORT': '9100'})

    importer._store_import_progress('client-5', 25.0, 12.5, '2024-01-01')

    assert calls == [(
        '9100|candle-import-progress|client-5',
        {'current': 25.0, 'estimated_remaining_seconds': 12.5, 'current_date': '2024-01-01'},
        86400,
    )]

    monkeypatch.setattr(importer.sync_redis, 'set', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('down')))
    importer._store_import_progress('client-5', 50.0, 5.0, '2024-01-02')


def test_fill_absent_candles_uses_open_before_first_and_close_afterward():
    start = 1_700_000_040_000
    candles = [
        {
            'id': 'present-1', 'exchange': 'Sandbox', 'symbol': 'BTC-USDT', 'timeframe': '1m',
            'timestamp': start + 60_000, 'open': 10.0, 'close': 12.0,
            'high': 13.0, 'low': 9.0, 'volume': 5.0,
        },
        {
            'id': 'present-2', 'exchange': 'Sandbox', 'symbol': 'BTC-USDT', 'timeframe': '1m',
            'timestamp': start + 180_000, 'open': 14.0, 'close': 15.0,
            'high': 16.0, 'low': 13.0, 'volume': 6.0,
        },
    ]

    result = importer._fill_absent_candles(candles, start, start + 240_000)

    assert [c['timestamp'] for c in result] == [start + i * 60_000 for i in range(5)]
    assert (result[0]['open'], result[0]['close'], result[0]['high'], result[0]['low'], result[0]['volume']) == (
        10.0, 10.0, 10.0, 10.0, 0,
    )
    assert result[2]['open'] == result[2]['close'] == result[2]['high'] == result[2]['low'] == 12.0
    assert result[2]['volume'] == 0
    assert result[4]['open'] == result[4]['close'] == result[4]['high'] == result[4]['low'] == 15.0
    assert result[4]['volume'] == 0


def test_fill_absent_candles_rejects_large_synthetic_tail():
    start = 1_700_000_040_000
    candles = [
        {
            'id': 'present-1', 'exchange': 'Sandbox', 'symbol': 'BTC-USDT', 'timeframe': '1m',
            'timestamp': start, 'open': 10.0, 'close': 12.0,
            'high': 13.0, 'low': 9.0, 'volume': 5.0,
        },
        {
            'id': 'present-2', 'exchange': 'Sandbox', 'symbol': 'BTC-USDT', 'timeframe': '1m',
            'timestamp': start + 60_000, 'open': 12.0, 'close': 14.0,
            'high': 15.0, 'low': 11.0, 'volume': 6.0,
        },
    ]

    with pytest.raises(exceptions.CandleNotFoundInExchange, match='incomplete trailing range'):
        importer._fill_absent_candles(candles, start, start + 102 * 60_000)


def test_fill_absent_candles_allows_bounded_synthetic_tail():
    start = 1_700_000_040_000
    candles = [{
        'id': 'present-1', 'exchange': 'Sandbox', 'symbol': 'BTC-USDT', 'timeframe': '1m',
        'timestamp': start, 'open': 10.0, 'close': 12.0,
        'high': 13.0, 'low': 9.0, 'volume': 5.0,
    }]

    result = importer._fill_absent_candles(
        candles, start, start + importer.MAX_MISSING_EDGE_MINUTES * 60_000,
    )

    assert len(result) == importer.MAX_MISSING_EDGE_MINUTES + 1
    assert result[-1]['timestamp'] == start + importer.MAX_MISSING_EDGE_MINUTES * 60_000
    assert result[-1]['open'] == result[-1]['close'] == 12.0
    assert result[-1]['volume'] == 0


def test_backup_exchange_reuses_exact_database_range(monkeypatch):
    start = 1_700_000_040_000
    state = {
        'range': None,
        'counts': {},
        'tuples': [
            (start, 1.0, 2.0, 3.0, 0.5, 4.0),
            (start + 60_000, 2.0, 3.0, 4.0, 1.5, 5.0),
        ],
    }
    backup = _FakeDriver([], count=2)
    monkeypatch.setattr(importer, 'Candle', _candle_model(state))

    result = importer._get_candles_from_backup_exchange(
        'Primary Provider', backup, 'BTC-USDT', start, start + 60_000,
    )

    assert [c['timestamp'] for c in result] == [start, start + 60_000]
    assert all(c['exchange'] == 'Primary Provider' for c in result)
    assert result[0] | {'id': '<generated>'} == {
        'id': '<generated>', 'exchange': 'Primary Provider', 'symbol': 'BTC-USDT',
        'timeframe': '1m', 'timestamp': start, 'open': 1.0, 'close': 2.0,
        'high': 3.0, 'low': 0.5, 'volume': 4.0,
    }


def test_backup_exchange_fetches_and_stores_when_database_range_is_absent(monkeypatch):
    start = arrow.get('2024-01-01T00:00:00Z').int_timestamp * 1000
    state = {'range': None, 'counts': {}, 'tuples': []}
    fetches = []
    backup = _FakeDriver(fetches, count=2)
    monkeypatch.setattr(importer, 'Candle', _candle_model(state))
    monkeypatch.setattr(importer.jh, 'now_to_timestamp', lambda: start + 119_999)
    monkeypatch.setattr(importer.time, 'sleep', lambda seconds: None)

    def store(candles):
        state['tuples'] = [
            (c['timestamp'], c['open'], c['close'], c['high'], c['low'], c['volume'])
            for c in candles
        ]

    monkeypatch.setattr(importer, 'store_candles_list', store)

    result = importer._get_candles_from_backup_exchange(
        'Primary Provider', backup, 'BTC-USDT', start, start + 60_000,
    )

    assert fetches == [('BTC-USDT', start, '1m')]
    assert len(result) == 2
    assert all(c['exchange'] == 'Primary Provider' for c in result)
