import json
from types import SimpleNamespace

import jesse.helpers as jh
from jesse.controllers import live_controller
from jesse.services import live_chart_service
from jesse.services.web import GetLiveSessionChartDataRequestJson


def session(finished_at=1_700_100_000_000):
    return SimpleNamespace(
        id='session-1',
        exchange='Sandbox',
        created_at=1_700_000_000_000,
        finished_at=finished_at,
        state='{}',
        state_json={
            'form': {
                'routes': [
                    {'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'Demo'},
                ],
            },
        },
    )


def test_live_chart_data_builds_a_bounded_route_snapshot(monkeypatch):
    fake_session = session()
    candles = [
        (1_700_099_940_000, 100.0, 101.0, 102.0, 99.0, 12.0),
        (1_700_100_000_000, 101.0, 103.0, 104.0, 100.0, 14.0),
    ]
    executed_order = SimpleNamespace(status='EXECUTED', executed_at=1_700_099_950_000)
    active_order = SimpleNamespace(status='ACTIVE', executed_at=None)
    closed_trade = SimpleNamespace(
        exchange='Sandbox', symbol='BTC-USDT', closed_at=1_700_099_980_000,
    )
    open_trade = SimpleNamespace(exchange='Sandbox', symbol='BTC-USDT', closed_at=None)

    monkeypatch.setattr(live_chart_service.candle_repository, 'fetch_candles_from_db', lambda *args: candles)
    monkeypatch.setattr(live_chart_service.order_repository, 'get_session_orders', lambda *args: [executed_order, active_order])
    monkeypatch.setattr(live_chart_service.closed_trade_repository, 'find_by_session_id', lambda *args: [closed_trade, open_trade])
    monkeypatch.setattr(live_chart_service.transformers, 'get_order_details', lambda order: {'id': 'order-1'})
    monkeypatch.setattr(live_chart_service.transformers, 'get_closed_trade_details', lambda trade: {'id': 'trade-1'})
    monkeypatch.setattr(live_chart_service, 'get_live_charts_snapshot', lambda session_id: {
        jh.key('Sandbox', 'BTC-USDT', '1m'): {
            'lines': {
                'EMA': {
                    'data': [
                        {'time': 1_699_999_999, 'value': 99},
                        {'time': 1_700_099_940, 'value': 100},
                    ],
                },
            },
            'extra_charts': {
                'ADX': {
                    'adx': {'data': [{'time': 1_699_999_999, 'value': 20}]},
                },
            },
        },
    })

    result = live_chart_service.get_live_session_chart_data(
        fake_session,
        'Sandbox',
        'BTC-USDT',
        '1m',
        candle_count=1000,
    )

    assert result['candles'][-1] == {
        'time': 1_700_100_000,
        'open': 101.0,
        'close': 103.0,
        'high': 104.0,
        'low': 100.0,
        'volume': 14.0,
    }
    assert result['orders'] == [{'id': 'order-1'}]
    assert result['trades'] == [{'id': 'trade-1'}]
    assert result['strategy_charts']['lines']['EMA']['data'] == [
        {'time': 1_700_099_940, 'value': 100},
    ]
    assert result['strategy_charts']['extra_charts'] == {}
    assert result['window']['candle_count'] == 1000


def test_live_chart_data_rejects_routes_outside_the_session():
    try:
        live_chart_service.get_live_session_chart_data(
            session(), 'Sandbox', 'ETH-USDT', '1m'
        )
    except ValueError as e:
        assert str(e) == 'The requested route does not belong to this live session.'
    else:
        raise AssertionError('Expected an invalid route error')


def test_live_chart_data_centers_an_older_anchor_and_caps_the_request(monkeypatch):
    fake_session = session()
    captured = {}

    def fetch(exchange, symbol, timeframe, start, finish):
        captured.update(start=start, finish=finish)
        return []

    monkeypatch.setattr(live_chart_service.candle_repository, 'fetch_candles_from_db', fetch)
    monkeypatch.setattr(live_chart_service.order_repository, 'get_session_orders', lambda *args: [])
    monkeypatch.setattr(live_chart_service.closed_trade_repository, 'find_by_session_id', lambda *args: [])
    monkeypatch.setattr(live_chart_service, 'get_live_charts_snapshot', lambda session_id: {})

    anchor = 1_700_050_000_000
    result = live_chart_service.get_live_session_chart_data(
        fake_session,
        'Sandbox',
        'BTC-USDT',
        '1m',
        anchor_time=anchor,
        candle_count=100_000,
    )

    assert result['window']['candle_count'] == live_chart_service.MAX_CANDLE_COUNT
    assert captured['start'] < anchor < captured['finish']


def test_live_chart_data_merges_durable_history_with_the_redis_tail(monkeypatch):
    fake_session = session()
    monkeypatch.setattr(live_chart_service.candle_repository, 'fetch_candles_from_db', lambda *args: [])
    monkeypatch.setattr(live_chart_service.order_repository, 'get_session_orders', lambda *args: [])
    monkeypatch.setattr(live_chart_service.closed_trade_repository, 'find_by_session_id', lambda *args: [])
    monkeypatch.setattr(live_chart_service.live_chart_repository, 'get_chart_data', lambda *args: {
        'lines': {
            'EMA': {
                'color': 'blue',
                'data': [
                    {'time': 1_700_099_880, 'value': 98, 'color': 'blue'},
                    {'time': 1_700_099_940, 'value': 99, 'color': 'blue'},
                ],
            },
        },
        'horizontal_lines': {},
        'extra_charts': {},
        'horizontal_extra_lines': {},
    })
    monkeypatch.setattr(live_chart_service, 'get_live_charts_snapshot', lambda session_id: {
        jh.key('Sandbox', 'BTC-USDT', '1m'): {
            'lines': {
                'EMA': {
                    'color': 'green',
                    'data': [
                        {'time': 1_700_099_940, 'value': 100, 'color': 'green'},
                        {'time': 1_700_100_000, 'value': 101, 'color': 'green'},
                    ],
                },
            },
            'horizontal_lines': {},
            'extra_charts': {},
            'horizontal_extra_lines': {},
        },
    })

    result = live_chart_service.get_live_session_chart_data(
        fake_session, 'Sandbox', 'BTC-USDT', '1m'
    )

    assert result['strategy_charts']['lines']['EMA'] == {
        'color': 'green',
        'data': [
            {'time': 1_700_099_880, 'value': 98, 'color': 'blue'},
            {'time': 1_700_099_940, 'value': 100, 'color': 'green'},
            {'time': 1_700_100_000, 'value': 101, 'color': 'green'},
        ],
    }


def test_historical_window_keeps_its_stored_horizontal_value(monkeypatch):
    monkeypatch.setattr(live_chart_service.live_chart_repository, 'get_chart_data', lambda *args: {
        'lines': {},
        'horizontal_lines': {
            'level': {'title': 'level', 'price': 25, 'color': 'red', 'lineWidth': 1.5, 'lineStyle': 0},
        },
        'extra_charts': {},
        'horizontal_extra_lines': {},
    })
    monkeypatch.setattr(live_chart_service, 'get_live_charts_snapshot', lambda session_id: {
        'route-key': {
            'lines': {},
            'horizontal_lines': {
                'level': {'title': 'level', 'price': 30, 'color': 'red', 'lineWidth': 1.5, 'lineStyle': 0},
            },
            'extra_charts': {},
            'horizontal_extra_lines': {},
        },
    })

    result = live_chart_service._strategy_charts_for_window(
        'session-1',
        'Sandbox',
        'BTC-USDT',
        '1m',
        'route-key',
        60_000,
        120_000,
        False,
    )

    assert result['horizontal_lines']['level']['price'] == 25


def test_live_chart_data_endpoint_returns_service_payload(monkeypatch):
    fake_session = session()
    payload = {'candles': [], 'orders': [], 'trades': []}
    monkeypatch.setattr(live_controller.live_session_repository, 'get_live_session_by_id', lambda session_id: fake_session)
    monkeypatch.setattr(live_chart_service, 'get_live_session_chart_data', lambda *args: payload)

    response = live_controller.get_live_session_chart_data(
        'session-1',
        GetLiveSessionChartDataRequestJson(
            exchange='Sandbox',
            symbol='BTC-USDT',
            timeframe='1m',
        ),
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'chart_data': payload}


def test_live_chart_data_route_is_registered_as_post():
    chart_route = next(
        item for item in live_controller.router.routes
        if item.path == '/live/sessions/{session_id}/chart-data'
    )

    assert chart_route.methods == {'POST'}
    assert [dependency.call for dependency in chart_route.dependant.dependencies] == [
        live_controller.require_auth,
    ]
