from importlib import import_module
from types import SimpleNamespace

import pytest


session_model = import_module('jesse.models.SignificanceTestSession')
significance_test_mode = import_module('jesse.modes.significance_test_mode')


def test_orphaned_running_session_is_reconciled_as_stopped(monkeypatch):
    session = SimpleNamespace(
        id='5a621676-102d-4f3f-ac73-7801a622fdab',
        status='running',
    )
    status_updates = []

    monkeypatch.setattr(session_model.jh, 'is_unit_testing', lambda: False)
    monkeypatch.setattr('jesse.services.redis.is_process_active', lambda session_id: False)
    monkeypatch.setattr(
        session_model,
        'update_significance_test_session_status',
        lambda session_id, status: status_updates.append((session_id, status)),
    )

    reconciled = session_model._reconcile_significance_test_session_status(session)

    assert reconciled.status == 'stopped'
    assert status_updates == [(str(session.id), 'stopped')]


def test_validation_failure_persists_exception_and_stops_session(monkeypatch):
    session_id = '5a621676-102d-4f3f-ac73-7801a622fdab'
    exceptions = []
    status_updates = []

    monkeypatch.setattr('jesse.config.set_config', lambda config: None)
    monkeypatch.setattr(significance_test_mode.router, 'initiate', lambda routes, data_routes: None)
    monkeypatch.setattr(significance_test_mode.store.app, 'set_session_id', lambda value: None)
    monkeypatch.setattr(significance_test_mode, 'register_custom_exception_handler', lambda: None)
    monkeypatch.setattr(
        significance_test_mode,
        'validate_routes',
        lambda router: (_ for _ in ()).throw(RuntimeError('validation failed')),
    )
    monkeypatch.setattr(
        significance_test_mode,
        'store_significance_test_exception',
        lambda value, error, traceback: exceptions.append((value, error, traceback)),
    )
    monkeypatch.setattr(
        significance_test_mode,
        'update_significance_test_session_status',
        lambda value, status: status_updates.append((value, status)),
    )

    with pytest.raises(RuntimeError, match='validation failed'):
        significance_test_mode.run(
            session_id=session_id,
            user_config={},
            exchange='Sandbox',
            routes=[{
                'symbol': 'BTC-USDT',
                'timeframe': '4h',
                'strategy': 'Missing',
            }],
            data_routes=[],
            start_date='2025-01-01',
            finish_date='2025-02-01',
            n_simulations=10,
            random_seed=42,
            theme='light',
            state={},
        )

    assert status_updates == [(session_id, 'stopped')]
    assert len(exceptions) == 1
    assert exceptions[0][0] == session_id
    assert exceptions[0][1] == 'RuntimeError: validation failed'
    assert 'RuntimeError: validation failed' in exceptions[0][2]
