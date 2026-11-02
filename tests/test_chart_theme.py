import json
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jesse.controllers import backtest_controller, significance_test_controller
from jesse.models.Option import Option
from jesse.modes import data_provider
from jesse.services import auth


PASSWORD = 'chart-theme-password'


def _headers() -> dict:
    return {'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()}


def _store_config(monkeypatch, config: dict | None) -> None:
    row = None if config is None else SimpleNamespace(json=json.dumps(config))
    monkeypatch.setattr(Option, 'get_or_none', lambda *args: row)


@pytest.mark.parametrize(
    ('config', 'expected'),
    [
        ({'theme': 'dark'}, 'dark'),
        ({'theme': 'light'}, 'light'),
        ({'theme': 'sepia'}, 'light'),
        ({}, 'light'),
        (None, 'light'),
    ],
)
def test_chart_theme_comes_from_the_stored_settings(monkeypatch, config, expected):
    _store_config(monkeypatch, config)

    assert data_provider.get_chart_theme() == expected


def _route() -> dict:
    return {'exchange': 'Sandbox', 'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'Test19'}


def _backtest_payload(**overrides) -> dict:
    return {
        'id': 'backtest-id',
        'exchange': 'Sandbox',
        'routes': [_route()],
        'data_routes': [],
        'config': {'warm_up_candles': 0},
        'start_date': '2024-01-01',
        'finish_date': '2024-01-02',
        'debug_mode': False,
        'export_csv': False,
        'export_json': False,
        'export_chart': False,
        'fast_mode': False,
        'benchmark': False,
        'state': {},
        **overrides,
    }


@pytest.fixture
def backtest_client(monkeypatch) -> tuple:
    """Accept backtests without touching the database, recording what reaches the worker."""
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    started = []
    monkeypatch.setattr(backtest_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(backtest_controller, 'update_backtest_session_state', lambda *args: None)
    monkeypatch.setattr(backtest_controller, 'update_backtest_session_status', lambda *args: None)
    monkeypatch.setattr(backtest_controller.session_liveness, 'claim', lambda *args: None)
    monkeypatch.setattr(backtest_controller.process_manager, 'add_task', lambda *args: started.append(args))
    monkeypatch.setattr(backtest_controller, 'get_chart_theme', lambda: 'dark')

    app = FastAPI()
    app.include_router(backtest_controller.router)
    return TestClient(app), started


def test_a_backtest_without_a_theme_uses_the_stored_one(backtest_client):
    # regression: backtests started through MCP sent no theme, so their chart
    # images were always light.
    client, started = backtest_client

    response = client.post('/backtest', json=_backtest_payload(), headers=_headers())

    assert response.status_code == 202
    assert started[0][-2] == 'dark'


def test_a_backtest_keeps_the_theme_it_was_sent(backtest_client):
    client, started = backtest_client

    response = client.post('/backtest', json=_backtest_payload(theme='light'), headers=_headers())

    assert response.status_code == 202
    assert started[0][-2] == 'light'


def test_a_backtest_keeps_its_report_only_when_asked(backtest_client):
    client, started = backtest_client

    client.post('/backtest', json=_backtest_payload(), headers=_headers())
    client.post('/backtest', json=_backtest_payload(export_pdf=True), headers=_headers())

    assert [arguments[-1] for arguments in started] == [False, True]


def test_a_significance_test_without_a_theme_uses_the_stored_one(monkeypatch):
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    started = []
    stored = []
    monkeypatch.setattr(significance_test_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(significance_test_controller, 'get_significance_test_session_by_id', lambda session_id: None)
    monkeypatch.setattr(significance_test_controller, 'store_significance_test_session', lambda **kwargs: stored.append(kwargs))
    monkeypatch.setattr(significance_test_controller, 'get_chart_theme', lambda: 'dark')
    monkeypatch.setattr(significance_test_controller.process_manager, 'add_task', lambda *args: started.append(args))
    monkeypatch.setattr(significance_test_controller.session_liveness, 'claim', lambda *args: None)

    app = FastAPI()
    app.include_router(significance_test_controller.router)
    response = TestClient(app).post(
        '/significance-test',
        json={
            'id': 'test-id',
            'exchange': 'Sandbox',
            'routes': [_route()],
            'data_routes': [],
            'config': {},
            'start_date': '2024-01-01',
            'finish_date': '2024-01-02',
            'state': {},
        },
        headers=_headers(),
    )

    assert response.status_code == 202
    assert stored[0]['theme'] == 'dark'
    assert 'dark' in started[0]
