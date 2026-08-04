import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient

from jesse.controllers import backtest_controller
from jesse.services.web import (
    GetBacktestSessionChartDataRequestJson,
    fastapi_app,
)


def _request(symbol: str = 'ETH-USDT') -> GetBacktestSessionChartDataRequestJson:
    return GetBacktestSessionChartDataRequestJson(
        exchange='Sandbox',
        symbol=symbol,
        timeframe='5m',
    )


def _route(symbol: str, field: str, value) -> dict:
    return {
        'exchange': 'Sandbox',
        'symbol': symbol,
        'timeframe': '5m',
        field: value,
    }


def test_backtest_chart_data_selects_one_route_and_orders_series(monkeypatch):
    stored = {
        'candles_chart': [
            _route('BTC-USDT', 'candles', [{'time': 60}]),
            _route('ETH-USDT', 'candles', [
                {'time': 180, 'open': 3},
                {'time': 120, 'open': 2},
            ]),
        ],
        'orders_chart': [
            _route('ETH-USDT', 'orders', [
                {'time': 180, 'order_id': 'later'},
                {'time': 120, 'order_id': 'b'},
                {'time': 120, 'order_id': 'a'},
            ]),
        ],
        'add_line_to_candle_chart': [
            _route('ETH-USDT', 'lines', {
                'EMA': {'data': [{'time': 120, 'value': float('nan')}]},
            }),
        ],
        'add_extra_line_chart': [
            _route('ETH-USDT', 'charts', {'ADX': {'adx': {'data': []}}}),
        ],
        'add_horizontal_line_to_candle_chart': [
            _route('ETH-USDT', 'lines', {'entry': {'price': 100}}),
        ],
        'add_horizontal_line_to_extra_chart': [
            _route('ETH-USDT', 'lines', {'ADX': {'threshold': {'price': 25}}}),
        ],
    }
    monkeypatch.setattr(
        backtest_controller,
        'get_backtest_session_by_id_from_db',
        lambda session_id: SimpleNamespace(chart_data=json.dumps(stored)),
    )

    response = backtest_controller.get_backtest_session_chart_data(uuid4(), _request())
    payload = json.loads(response.body)['chart_data']

    assert payload['route'] == {
        'exchange': 'Sandbox',
        'symbol': 'ETH-USDT',
        'timeframe': '5m',
    }
    assert [candle['time'] for candle in payload['candles']] == [120, 180]
    assert [order['order_id'] for order in payload['orders']] == ['a', 'b', 'later']
    assert payload['strategy_charts'] == {
        'lines': {'EMA': {'data': [{'time': 120, 'value': None}]}},
        'horizontal_lines': {'entry': {'price': 100}},
        'extra_charts': {'ADX': {'adx': {'data': []}}},
        'horizontal_extra_lines': {'ADX': {'threshold': {'price': 25}}},
    }


def test_backtest_chart_data_returns_null_when_route_has_no_candles(monkeypatch):
    stored = {
        'candles_chart': [_route('BTC-USDT', 'candles', [{'time': 60}])],
        'orders_chart': [_route('ETH-USDT', 'orders', [{'time': 60}])],
    }
    monkeypatch.setattr(
        backtest_controller,
        'get_backtest_session_by_id_from_db',
        lambda session_id: SimpleNamespace(chart_data=json.dumps(stored)),
    )

    response = backtest_controller.get_backtest_session_chart_data(uuid4(), _request())

    assert json.loads(response.body) == {'chart_data': None}


def test_backtest_chart_data_returns_404_for_missing_session(monkeypatch):
    session_id = uuid4()
    monkeypatch.setattr(
        backtest_controller,
        'get_backtest_session_by_id_from_db',
        lambda requested_id: None,
    )

    response = backtest_controller.get_backtest_session_chart_data(session_id, _request())

    assert response.status_code == 404
    assert json.loads(response.body) == {
        'error': f'Session with ID {session_id} not found',
    }


def test_backtest_chart_data_route_is_an_authenticated_post():
    chart_route = next(
        item for item in backtest_controller.router.routes
        if item.path == '/backtest/sessions/{session_id}/chart-data'
    )

    assert chart_route.methods == {'POST'}
    assert [dependency.call for dependency in chart_route.dependant.dependencies] == [
        backtest_controller.require_auth,
    ]


def test_http_gzip_middleware_compresses_large_responses():
    configured = next(
        middleware for middleware in fastapi_app.user_middleware
        if middleware.cls is GZipMiddleware
    )
    app = FastAPI()
    app.add_middleware(configured.cls, *configured.args, **configured.kwargs)

    @app.get('/large-response')
    def large_response():
        return {'data': 'x' * 4096}

    response = TestClient(app).get(
        '/large-response',
        headers={'Accept-Encoding': 'gzip'},
    )

    assert configured.kwargs == {'minimum_size': 1024, 'compresslevel': 5}
    assert response.status_code == 200
    assert response.headers['content-encoding'] == 'gzip'
    assert response.json() == {'data': 'x' * 4096}
