import json
from types import SimpleNamespace

import pytest

from jesse.models.Option import Option
from jesse.modes import data_provider
from jesse.repositories import candle_repository, live_session_repository
from jesse.services.db import database


GLOBAL = {'warm_up_candles': 10, 'generate_candles_from_1m': True}
SESSION_ID = 'a6e2d1e0-2f5f-4b1e-9f3c-111111111111'


@pytest.fixture
def fetched(monkeypatch):
    """Serve stored settings and record which timeframe and window get_candles reads."""
    calls = []

    def fetch(exchange, symbol, timeframe, start_date, finish_date):
        calls.append({'timeframe': timeframe, 'start': start_date, 'finish': finish_date})
        return [[0, 1, 2, 3, 0.5, 10]]

    monkeypatch.setattr(database, 'open_connection', lambda: None)
    monkeypatch.setattr(database, 'close_connection', lambda: None)
    monkeypatch.setattr(Option, 'get', lambda *args: SimpleNamespace(json=json.dumps({'live': GLOBAL})))
    monkeypatch.setattr(candle_repository, 'fetch_candles_from_db', fetch)
    return calls


def _session_with(monkeypatch, config) -> None:
    session = SimpleNamespace(state_json={'form': {'config': config}})
    monkeypatch.setattr(
        live_session_repository, 'get_live_session_by_id',
        lambda session_id: session if session_id == SESSION_ID else None,
    )


def test_chart_reads_the_candles_of_the_sessions_own_setting(monkeypatch, fetched):
    # regression: the chart followed the global setting, so a session started without 1m
    # generation showed nothing once the global setting was on, as no 1m rows are stored.
    _session_with(monkeypatch, {'warm_up_candles': 10, 'generate_candles_from_1m': False})

    data_provider.get_candles('Gate USDT Perpetual', 'BTC-USDT', '15m', SESSION_ID)

    assert fetched[0]['timeframe'] == '15m'


def test_chart_reads_one_minute_candles_for_a_session_that_generates_them(monkeypatch, fetched):
    monkeypatch.setattr(Option, 'get', lambda *args: SimpleNamespace(json=json.dumps({
        'live': {**GLOBAL, 'generate_candles_from_1m': False},
    })))
    _session_with(monkeypatch, {'warm_up_candles': 10, 'generate_candles_from_1m': True})

    data_provider.get_candles('Gate USDT Perpetual', 'BTC-USDT', '1m', SESSION_ID)

    assert fetched[0]['timeframe'] == '1m'


def test_chart_covers_the_sessions_own_warm_up(monkeypatch, fetched):
    _session_with(monkeypatch, {'warm_up_candles': 300, 'generate_candles_from_1m': False})

    data_provider.get_candles('Gate USDT Perpetual', 'BTC-USDT', '15m', SESSION_ID)
    data_provider.get_candles('Gate USDT Perpetual', 'BTC-USDT', '15m')

    session_call, global_call = fetched
    assert session_call['start'] < global_call['start']


@pytest.mark.parametrize('session_id', [None, 'not-a-session'])
def test_other_callers_use_the_global_setting(monkeypatch, fetched, session_id):
    _session_with(monkeypatch, {'warm_up_candles': 10, 'generate_candles_from_1m': False})

    data_provider.get_candles('Gate USDT Perpetual', 'BTC-USDT', '1m', session_id)

    assert fetched[0]['timeframe'] == '1m'


def test_an_id_that_cannot_be_a_session_is_never_looked_up(monkeypatch, fetched):
    # regression: looking one up failed the query and broke the connection's next one
    looked_up = []
    monkeypatch.setattr(live_session_repository, 'get_live_session_by_id', looked_up.append)

    data_provider.get_candles('Gate USDT Perpetual', 'BTC-USDT', '1m', 'not-a-session')

    assert looked_up == []


def test_a_session_from_before_this_setting_was_stored_uses_the_global_one(monkeypatch, fetched):
    _session_with(monkeypatch, None)

    data_provider.get_candles('Gate USDT Perpetual', 'BTC-USDT', '1m', SESSION_ID)

    assert fetched[0]['timeframe'] == '1m'
