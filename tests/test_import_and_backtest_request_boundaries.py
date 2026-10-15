import json
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jesse import exceptions
from jesse.controllers import backtest_controller, candles_controller
from jesse.mcp.tools.services import candles as mcp_candles_service
from jesse.modes import backtest_mode, import_candles_mode
from jesse.services import auth, redis


PASSWORD = 'request-boundary-password'
AUTHORIZATION = sha256(PASSWORD.encode('utf-8')).hexdigest()


@pytest.fixture
def api_client(monkeypatch) -> TestClient:
    """Build the real routers with production authentication and error shape."""
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(candles_controller.router)
    app.include_router(backtest_controller.router)
    return TestClient(app)


def _headers() -> dict:
    return {'Authorization': AUTHORIZATION}


def _import_payload() -> dict:
    return {
        'id': 'import-id',
        'exchange': 'Binance Spot',
        'symbol': 'BTC-USDT',
        'start_date': '2024-01-01',
    }


def _backtest_payload(session_id: str = 'backtest-id') -> dict:
    form = {
        'exchange': 'Sandbox',
        'routes': [{
            'exchange': 'Sandbox',
            'symbol': 'BTC-USDT',
            'timeframe': '1m',
            'strategy': 'Test19',
        }],
        'data_routes': [],
        'config': {'warm_up_candles': 0},
        'start_date': '2024-01-01',
        'finish_date': '2024-01-02',
        'debug_mode': False,
        'export_csv': False,
        'export_json': False,
        'export_chart': False,
        'fast_mode': True,
        'benchmark': False,
        'theme': 'light',
    }
    return {**form, 'id': session_id, 'state': {'form': form}}


@pytest.mark.parametrize(
    ('path', 'payload'),
    [
        ('/candles/import', _import_payload()),
        ('/candles/import-status', {'id': 'import-id'}),
        ('/candles/cancel-import', {'id': 'import-id'}),
        ('/backtest', _backtest_payload()),
        ('/backtest/cancel', {'id': 'backtest-id'}),
    ],
)
def test_import_and_backtest_mutations_require_authentication(api_client, path, payload):
    response = api_client.post(path, json=payload)

    assert response.status_code == 401
    assert response.json() == {'message': 'Invalid password'}


@pytest.mark.parametrize(
    ('path', 'payload'),
    [
        ('/candles/import', {'id': 'import-id'}),
        ('/backtest', {'id': 'backtest-id'}),
    ],
)
def test_invalid_requests_are_rejected_before_a_worker_starts(
    monkeypatch,
    api_client,
    path,
    payload,
):
    starts = []
    monkeypatch.setattr(
        candles_controller.process_manager,
        'add_task',
        lambda *args: starts.append(args),
    )

    response = api_client.post(path, json=payload, headers=_headers())

    assert response.status_code == 422
    assert response.json()['detail']
    assert starts == []


def test_import_start_validates_and_publishes_running_before_worker(
    monkeypatch,
    api_client,
):
    events = []
    monkeypatch.setattr(candles_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(
        import_candles_mode,
        'validate_import_request',
        lambda exchange, symbol, start_date: events.append(('validate', exchange, symbol, start_date)),
    )
    monkeypatch.setattr(
        import_candles_mode,
        'store_import_outcome',
        lambda client_id, status, *args: events.append(('outcome', client_id, status)),
    )
    monkeypatch.setattr(
        candles_controller.process_manager,
        'add_task',
        lambda *args: events.append(('worker', args[1])),
    )

    response = api_client.post('/candles/import', json=_import_payload(), headers=_headers())

    assert response.status_code == 202
    assert events == [
        ('validate', 'Binance Spot', 'BTC-USDT', '2024-01-01'),
        ('outcome', 'import-id', 'running'),
        ('worker', 'import-id'),
    ]


def test_import_validation_error_is_serialized_without_starting_worker(
    monkeypatch,
    api_client,
):
    outcomes = []
    starts = []
    monkeypatch.setattr(candles_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(
        import_candles_mode,
        'validate_import_request',
        lambda *args: (_ for _ in ()).throw(ValueError('unsupported import request')),
    )
    monkeypatch.setattr(
        import_candles_mode,
        'store_import_outcome',
        lambda client_id, status, error=None, *args: outcomes.append((status, error)),
    )
    monkeypatch.setattr(
        candles_controller.process_manager,
        'add_task',
        lambda *args: starts.append(args),
    )

    response = api_client.post('/candles/import', json=_import_payload(), headers=_headers())

    assert response.status_code == 422
    assert response.json() == {'error': 'ValueError: unsupported import request'}
    assert outcomes == [('failed', 'ValueError: unsupported import request')]
    assert starts == []


@pytest.mark.parametrize(
    'invalid_values',
    [
        {'exchange': 'Unsupported Exchange'},
        {'start_date': 'not-a-date'},
        {'symbol': 'BTCUSDT'},
    ],
)
def test_import_rejects_invalid_public_values_before_start(
    monkeypatch,
    api_client,
    invalid_values,
):
    starts = []
    payload = {**_import_payload(), **invalid_values}
    monkeypatch.setattr(candles_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(import_candles_mode, 'store_import_outcome', lambda *args: None)
    monkeypatch.setattr(
        candles_controller.process_manager,
        'add_task',
        lambda *args: starts.append(args),
    )

    response = api_client.post('/candles/import', json=payload, headers=_headers())

    assert response.status_code == 422
    assert response.json()['error'].startswith('ValueError:')
    assert starts == []


def test_backtest_rejects_reversed_date_range_before_start(
    monkeypatch,
    api_client,
):
    starts = []
    payload = _backtest_payload()
    payload['start_date'] = '2024-02-01'
    payload['finish_date'] = '2024-01-01'
    monkeypatch.setattr(
        backtest_controller.process_manager,
        'add_task',
        lambda *args: starts.append(args),
    )

    response = api_client.post('/backtest', json=payload, headers=_headers())

    assert response.status_code == 422
    assert 'start_date must be earlier' in response.text
    assert starts == []


def test_import_status_reports_progress_and_terminal_failure(
    monkeypatch,
    api_client,
):
    class FakeRedis:
        def __init__(self):
            self.deleted = []

        def get(self, key):
            return json.dumps({
                'current': 42,
                'estimated_remaining_seconds': 8,
                'current_date': '2024-01-15',
            })

        def delete(self, key):
            self.deleted.append(key)

    fake_redis = FakeRedis()
    monkeypatch.setattr(redis, 'sync_redis', fake_redis)
    monkeypatch.setattr(candles_controller, 'is_process_active', lambda client_id: True)
    monkeypatch.setattr(import_candles_mode, 'get_import_outcome', lambda client_id: {'status': 'running'})

    running = api_client.post(
        '/candles/import-status',
        json={'id': 'import-id'},
        headers=_headers(),
    )

    assert running.status_code == 200
    assert running.json() == {
        'import_id': 'import-id',
        'status': 'running',
        'progress': {
            'current': 42,
            'estimated_remaining_seconds': 8,
            'current_date': '2024-01-15',
        },
    }

    monkeypatch.setattr(candles_controller, 'is_process_active', lambda client_id: False)
    monkeypatch.setattr(
        import_candles_mode,
        'get_import_outcome',
        lambda client_id: {
            'status': 'failed',
            'error': 'RuntimeError: provider unavailable',
            'traceback': 'serialized traceback',
        },
    )

    failed = api_client.post(
        '/candles/import-status',
        json={'id': 'import-id'},
        headers=_headers(),
    )

    assert failed.status_code == 200
    assert failed.json() == {
        'import_id': 'import-id',
        'status': 'failed',
        'error': 'RuntimeError: provider unavailable',
        'traceback': 'serialized traceback',
    }
    assert fake_redis.deleted


def test_mcp_import_status_preserves_serialized_failure(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                'status': 'failed',
                'import_id': 'import-id',
                'error': 'RuntimeError: provider unavailable',
                'traceback': 'serialized traceback',
            }

    monkeypatch.setattr(mcp_candles_service, 'hash_password', lambda password: 'hashed')
    monkeypatch.setattr(
        mcp_candles_service.requests,
        'post',
        lambda *args, **kwargs: Response(),
    )
    monkeypatch.setattr(mcp_candles_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(mcp_candles_service.mcp_config, 'JESSE_PASSWORD', 'password')

    result = mcp_candles_service.get_candle_import_status_service('import-id')

    assert result == {
        'status': 'failed',
        'import_id': 'import-id',
        'error': 'RuntimeError: provider unavailable',
        'traceback': 'serialized traceback',
        'message': 'Import import-id failed: RuntimeError: provider unavailable',
    }


def test_import_cancellation_removes_marker_and_persists_terminal_status(
    monkeypatch,
    api_client,
):
    events = []
    monkeypatch.setattr(
        candles_controller.process_manager,
        'cancel_process',
        lambda client_id: events.append(('cancel', client_id)),
    )
    monkeypatch.setattr(
        import_candles_mode,
        'store_import_outcome',
        lambda client_id, status: events.append(('outcome', client_id, status)),
    )

    response = api_client.post(
        '/candles/cancel-import',
        json={'id': 'import-id'},
        headers=_headers(),
    )

    assert response.status_code == 202
    assert events == [
        ('cancel', 'import-id'),
        ('outcome', 'import-id', 'cancelled'),
    ]


def test_backtest_start_failure_is_persisted_and_serialized(
    monkeypatch,
    api_client,
):
    events = []
    monkeypatch.setattr(backtest_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(
        backtest_controller,
        'update_backtest_session_state',
        lambda session_id, state: events.append(('state', session_id)),
    )
    monkeypatch.setattr(
        backtest_controller,
        'update_backtest_session_status',
        lambda session_id, status: events.append(('status', status)),
    )
    monkeypatch.setattr(
        backtest_controller,
        'store_backtest_session_exception',
        lambda session_id, error, error_traceback: events.append(('error', error, error_traceback)),
    )
    monkeypatch.setattr(
        backtest_controller.process_manager,
        'add_task',
        lambda *args: (_ for _ in ()).throw(RuntimeError('worker start failed')),
    )

    response = api_client.post('/backtest', json=_backtest_payload(), headers=_headers())

    assert response.status_code == 500
    assert response.json()['error'] == 'RuntimeError: worker start failed'
    assert 'RuntimeError: worker start failed' in response.json()['traceback']
    assert [event[0] for event in events] == ['state', 'status', 'error', 'status']
    assert events[1] == ('status', 'running')
    assert events[-1] == ('status', 'stopped')


def test_backtest_cancellation_updates_process_and_session(
    monkeypatch,
    api_client,
):
    events = []
    monkeypatch.setattr(
        backtest_controller.process_manager,
        'cancel_process',
        lambda session_id: events.append(('cancel', session_id)),
    )
    monkeypatch.setattr(
        backtest_controller,
        'update_backtest_session_status',
        lambda session_id, status: events.append(('status', session_id, status)),
    )

    response = api_client.post(
        '/backtest/cancel',
        json={'id': 'backtest-id'},
        headers=_headers(),
    )

    assert response.status_code == 202
    assert events == [
        ('cancel', 'backtest-id'),
        ('status', 'backtest-id', 'cancelled'),
    ]


def test_backtest_session_read_serializes_terminal_failure(
    monkeypatch,
    api_client,
):
    session_id = uuid4()
    session = SimpleNamespace(
        id=session_id,
        status='stopped',
        metrics=None,
        equity_curve=None,
        trades=None,
        hyperparameters=None,
        chart_data=None,
        created_at=1,
        updated_at=2,
        execution_duration=None,
        state_json={'form': {'exchange': 'Sandbox'}},
        exception='RuntimeError: strategy failed',
        traceback='serialized traceback',
        title=None,
        description=None,
        strategy_codes_json={},
    )
    monkeypatch.setattr(
        backtest_controller,
        'get_backtest_session_by_id_from_db',
        lambda requested_id: session,
    )

    response = api_client.post(
        f'/backtest/sessions/{session_id}',
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()['session']
    assert body['status'] == 'stopped'
    assert body['exception'] == 'RuntimeError: strategy failed'
    assert body['traceback'] == 'serialized traceback'
    assert body['state'] == {'form': {'exchange': 'Sandbox'}}


def test_backtest_cancellation_is_checked_on_the_execution_path(monkeypatch):
    executions = []
    monkeypatch.setattr(backtest_mode.jh, 'is_unit_testing', lambda: False)
    monkeypatch.setattr(backtest_mode, 'is_process_active', lambda session_id: False)
    monkeypatch.setattr(backtest_mode, 'register_custom_exception_handler', lambda: None)
    monkeypatch.setattr(
        backtest_mode,
        '_execute_backtest',
        lambda *args, **kwargs: executions.append(args),
    )

    with pytest.raises(exceptions.Termination):
        backtest_mode.run(
            'backtest-id',
            False,
            {},
            'Sandbox',
            [],
            [],
            '2024-01-01',
            '2024-01-02',
        )

    assert executions == []


def test_backtest_runtime_failure_is_persisted_once_with_its_type(monkeypatch):
    events = []
    backtest_model = __import__(
        'jesse.models.BacktestSession',
        fromlist=['store_backtest_session'],
    )
    monkeypatch.setattr(backtest_mode.jh, 'is_unit_testing', lambda: True)
    monkeypatch.setattr(backtest_mode.jh, 'should_execute_silently', lambda: False)
    monkeypatch.setattr(backtest_mode.router, 'initiate', lambda routes, data_routes: None)
    monkeypatch.setattr(backtest_mode.router, 'routes', [])
    monkeypatch.setattr(backtest_mode.store, 'reset', lambda: None)
    monkeypatch.setattr(backtest_mode.store.app, 'set_session_id', lambda value: None)
    monkeypatch.setattr(backtest_mode.store.candles, 'init_storage', lambda size: None)
    monkeypatch.setattr(backtest_mode, 'validate_routes', lambda value: None)
    monkeypatch.setattr(backtest_mode.exchange_service, 'initialize_exchanges_state', lambda: None)
    monkeypatch.setattr(backtest_mode.order_service, 'initialize_orders_state', lambda: None)
    monkeypatch.setattr(backtest_mode.position_service, 'initialize_positions_state', lambda: None)
    monkeypatch.setattr(backtest_mode.stats, 'candles_info', lambda candles: {})
    monkeypatch.setattr(backtest_mode.stats, 'routes', lambda routes: [])
    monkeypatch.setattr(backtest_mode, 'sync_publish', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        backtest_mode,
        'simulator',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('strategy failed')),
    )
    monkeypatch.setattr(backtest_model, 'store_backtest_session', lambda **kwargs: None)
    monkeypatch.setattr(
        backtest_model,
        'store_backtest_session_exception',
        lambda session_id, error, error_traceback: events.append(('error', error, error_traceback)),
    )
    monkeypatch.setattr(
        backtest_model,
        'update_backtest_session_status',
        lambda session_id, status: events.append(('status', status)),
    )
    monkeypatch.setitem(
        backtest_mode.config['app'],
        'considering_candles',
        [('Sandbox', 'BTC-USDT')],
    )

    with pytest.raises(RuntimeError, match='strategy failed'):
        backtest_mode._execute_backtest(
            'backtest-id',
            False,
            {},
            'Sandbox',
            [],
            [],
            '2024-01-01',
            '2024-01-02',
            candles={'Sandbox-BTC-USDT': {'candles': []}},
        )

    assert len(events) == 2
    assert events[0][0:2] == ('error', 'RuntimeError: strategy failed')
    assert events[0][1] in events[0][2]
    assert events[1] == ('status', 'stopped')
