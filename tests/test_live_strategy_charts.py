import json
from types import SimpleNamespace

import numpy as np

import jesse.helpers as jh
from jesse.controllers import live_controller
from jesse.services import redis as redis_service
from jesse.services import report
from jesse.services.web import GetStrategyChartsRequestJson


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.set_calls = []

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.set_calls.append((key, value, ex))

    def get(self, key):
        return self.values.get(key)


def chart_data(line_data=None, extra_data=None):
    return SimpleNamespace(
        _add_line_to_candle_chart_values={
            'EMA': {'color': 'blue', 'data': line_data or []},
        },
        _add_horizontal_line_to_candle_chart_values={
            'entry': {'title': 'entry', 'price': 100, 'color': 'green'},
        },
        _add_extra_line_chart_values={
            'ADX': {'adx': {'color': 'orange', 'data': extra_data or []}},
            'Empty': {'empty': {'color': 'gray', 'data': []}},
        },
        _add_horizontal_line_to_extra_chart_values={
            'ADX': {'threshold': {'title': 'threshold', 'price': 25, 'color': 'red'}},
        },
    )


def route(strategy, symbol='BTC-USDT'):
    return SimpleNamespace(
        exchange='Sandbox',
        symbol=symbol,
        timeframe='1m',
        strategy=strategy,
    )


def test_strategy_chart_reports_skip_uninitialized_routes_and_empty_updates(monkeypatch):
    strategy = chart_data(
        line_data=[{'time': 60, 'value': 10, 'color': 'blue'}],
        extra_data=[{'time': 60, 'value': 20, 'color': 'orange'}],
    )
    monkeypatch.setattr(report.router, 'routes', [route(None), route(strategy)])

    key = jh.key('Sandbox', 'BTC-USDT', '1m')
    snapshot = report.strategy_charts()
    updates = report.strategy_charts_updates()

    assert list(snapshot) == [key]
    assert snapshot[key]['extra_charts']['Empty']['empty']['data'] == []
    assert updates[key]['lines'] == {
        'EMA': {'time': 60, 'value': 10, 'color': 'blue'},
    }
    assert updates[key]['extra_charts'] == {
        'ADX': {'adx': {'time': 60, 'value': 20, 'color': 'orange'}},
    }
    assert updates[key]['horizontal_lines']['entry']['price'] == 100
    assert updates[key]['horizontal_extra_lines']['ADX']['threshold']['price'] == 25


def test_strategy_chart_reports_keep_routes_separate(monkeypatch):
    btc = chart_data(line_data=[{'time': 60, 'value': 10, 'color': 'blue'}])
    eth = chart_data(line_data=[{'time': 60, 'value': 20, 'color': 'blue'}])
    monkeypatch.setattr(report.router, 'routes', [route(btc), route(eth, 'ETH-USDT')])

    updates = report.strategy_charts_updates()

    assert updates[jh.key('Sandbox', 'BTC-USDT', '1m')]['lines']['EMA']['value'] == 10
    assert updates[jh.key('Sandbox', 'ETH-USDT', '1m')]['lines']['EMA']['value'] == 20


def test_live_charts_key_is_scoped_to_the_app_port(monkeypatch):
    monkeypatch.setitem(redis_service.ENV_VALUES, 'APP_PORT', '9001')

    assert redis_service.live_charts_key('session-1') == '9001|live-charts:session-1'


def test_store_and_load_live_charts_snapshot(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(redis_service, 'sync_redis', fake_redis)
    monkeypatch.setitem(redis_service.ENV_VALUES, 'APP_PORT', '9001')
    charts = {
        'route': {
            'value': np.float64(12.5),
            'warming_up': np.float64('nan'),
        },
    }

    assert redis_service.store_live_charts_snapshot('session-1', charts) is True
    assert redis_service.get_live_charts_snapshot('session-1') == {
        'route': {'value': 12.5, 'warming_up': None},
    }

    key, raw, ttl = fake_redis.set_calls[0]
    assert key == '9001|live-charts:session-1'
    assert json.loads(raw)['route']['warming_up'] is None
    assert ttl == 60 * 60 * 24 * 7


def test_get_live_charts_snapshot_returns_empty_for_missing_or_invalid_data(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(redis_service, 'sync_redis', fake_redis)
    monkeypatch.setitem(redis_service.ENV_VALUES, 'APP_PORT', '9001')

    assert redis_service.get_live_charts_snapshot('missing') == {}

    fake_redis.values[redis_service.live_charts_key('invalid')] = b'not-json'
    assert redis_service.get_live_charts_snapshot('invalid') == {}


def test_redis_snapshot_failures_do_not_escape(monkeypatch):
    class BrokenRedis:
        def set(self, *args, **kwargs):
            raise ConnectionError('redis unavailable')

        def get(self, *args, **kwargs):
            raise ConnectionError('redis unavailable')

    messages = []
    monkeypatch.setattr(redis_service, 'sync_redis', BrokenRedis())
    monkeypatch.setattr(jh, 'terminal_debug', messages.append)

    assert redis_service.store_live_charts_snapshot('session-1', {}) is False
    assert redis_service.get_live_charts_snapshot('session-1') == {}
    assert len(messages) == 2
    assert all('Redis' in message for message in messages)


def test_strategy_charts_endpoint_returns_the_session_snapshot(monkeypatch):
    snapshot = {'route': {'lines': {'EMA': {'data': []}}}}
    monkeypatch.setattr(redis_service, 'get_live_charts_snapshot', lambda session_id: snapshot)

    response = live_controller.get_strategy_charts(
        GetStrategyChartsRequestJson(id='session-1')
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'id': 'session-1', 'data': snapshot}


def test_strategy_charts_route_is_registered_as_post():
    chart_route = next(
        item for item in live_controller.router.routes
        if item.path == '/live/strategy-charts'
    )

    assert chart_route.methods == {'POST'}
    assert [dependency.call for dependency in chart_route.dependant.dependencies] == [
        live_controller.require_auth,
    ]
