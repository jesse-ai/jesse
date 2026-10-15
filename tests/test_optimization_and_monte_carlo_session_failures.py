import asyncio
import json
from importlib import import_module
from types import SimpleNamespace

import pytest


optimization_model = import_module('jesse.models.OptimizationSession')
optimization_mode = import_module('jesse.modes.optimize_mode')
optimization_controller = import_module('jesse.controllers.optimization_controller')
monte_carlo_model = import_module('jesse.models.MonteCarloSession')
monte_carlo_mode = import_module('jesse.modes.monte_carlo_mode')
monte_carlo_controller = import_module('jesse.controllers.monte_carlo_controller')
transformers = import_module('jesse.services.transformers')


def test_monte_carlo_summary_metrics_allow_zero_valid_scenarios():
    # A completed run can legitimately have no valid scenarios, so its confidence
    # analysis has explanatory metadata but no metrics collection.
    results = json.dumps({
        'confidence_analysis': {
            'interpretation': 'No valid scenarios were available for analysis.',
        },
    })

    assert transformers._extract_candles_summary_metrics(results) == []
    assert transformers._extract_trades_summary_metrics(results) == []


@pytest.mark.parametrize(
    ('model', 'reconcile_name', 'update_name'),
    [
        (
            optimization_model,
            '_reconcile_optimization_session_status',
            'update_optimization_session_status',
        ),
        (
            monte_carlo_model,
            '_reconcile_monte_carlo_session_status',
            'update_monte_carlo_session_status',
        ),
    ],
)
def test_orphaned_worker_session_is_reconciled_as_stopped(
    monkeypatch,
    model,
    reconcile_name,
    update_name,
):
    session = SimpleNamespace(
        id='5a621676-102d-4f3f-ac73-7801a622fdab',
        status='running',
    )
    status_updates = []

    monkeypatch.setattr(model.jh, 'is_unit_testing', lambda: False)
    monkeypatch.setattr('jesse.services.redis.is_process_active', lambda session_id: False)
    monkeypatch.setattr(
        model,
        update_name,
        lambda session_id, status: status_updates.append((session_id, status)),
    )

    reconciled = getattr(model, reconcile_name)(session)

    assert reconciled.status == 'stopped'
    assert status_updates == [(str(session.id), 'stopped')]


def test_optimization_cpu_validation_failure_is_persisted(monkeypatch):
    session_id = '5a621676-102d-4f3f-ac73-7801a622fdab'
    exceptions = []
    status_updates = []

    monkeypatch.setattr(optimization_model, 'get_optimization_session_by_id', lambda value: object())
    monkeypatch.setattr(
        optimization_model,
        'add_session_exception',
        lambda value, error, traceback: exceptions.append((value, error, traceback)),
    )
    monkeypatch.setattr(
        optimization_model,
        'update_optimization_session_status',
        lambda value, status: status_updates.append((value, status)),
    )

    with pytest.raises(ValueError, match='cpu_cores'):
        optimization_mode.run(
            session_id=session_id,
            user_config={},
            exchange='Sandbox',
            routes=[],
            data_routes=[],
            training_start_date='2025-01-01',
            training_finish_date='2025-02-01',
            testing_start_date='2025-02-01',
            testing_finish_date='2025-03-01',
            optimal_total=10,
            fast_mode=True,
            cpu_cores=0,
            state={},
        )

    assert status_updates == [(session_id, 'stopped')]
    assert len(exceptions) == 1
    assert exceptions[0][1].startswith('ValueError: cpu_cores')
    assert 'ValueError: cpu_cores' in exceptions[0][2]


def test_optimization_controller_persists_session_before_worker_start(monkeypatch):
    session_id = '5a621676-102d-4f3f-ac73-7801a622fdab'
    events = []
    request = SimpleNamespace(
        id=session_id,
        config={},
        exchange='Sandbox',
        routes=[{'symbol': 'BTC-USDT'}],
        data_routes=[],
        training_start_date='2025-01-01',
        training_finish_date='2025-02-01',
        testing_start_date='2025-02-01',
        testing_finish_date='2025-03-01',
        optimal_total=10,
        fast_mode=True,
        cpu_cores=1,
        state={'form': {'id': session_id}},
    )

    monkeypatch.setattr(optimization_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(
        optimization_controller,
        'get_optimization_session_by_id_from_db',
        lambda value: None,
    )
    monkeypatch.setattr(
        optimization_controller,
        'store_optimization_session',
        lambda **kwargs: events.append(('store', kwargs)),
    )
    monkeypatch.setattr(
        optimization_controller,
        'update_optimization_session_state',
        lambda value, state: events.append(('state', value, state)),
    )
    monkeypatch.setattr(
        optimization_controller.process_manager,
        'add_task',
        lambda *args: events.append(('worker', args[1])),
    )

    asyncio.run(optimization_controller.optimization(request))

    assert [event[0] for event in events] == ['store', 'state', 'worker']


def test_monte_carlo_validation_failure_stops_parent_and_child(monkeypatch):
    session_id = '5a621676-102d-4f3f-ac73-7801a622fdab'
    status_updates = []
    exceptions = []

    monkeypatch.setattr('jesse.config.set_config', lambda config: None)
    monkeypatch.setattr(monte_carlo_mode.router, 'initiate', lambda routes, data_routes: None)
    monkeypatch.setattr(monte_carlo_mode.store.app, 'set_session_id', lambda value: None)
    monkeypatch.setattr(monte_carlo_mode, 'register_custom_exception_handler', lambda: None)
    monkeypatch.setattr(
        monte_carlo_mode,
        'validate_routes',
        lambda router: (_ for _ in ()).throw(RuntimeError('validation failed')),
    )
    monkeypatch.setattr(monte_carlo_mode, 'get_monte_carlo_session_by_id', lambda value: object())
    monkeypatch.setattr(
        monte_carlo_mode,
        'update_monte_carlo_session_status',
        lambda value, status: status_updates.append((value, status)),
    )
    monkeypatch.setattr(monte_carlo_mode, 'get_trades_session_by_parent_id', lambda value: None)
    monkeypatch.setattr(monte_carlo_mode, 'store_trades_session', lambda parent_id, total: 'trades-id')
    monkeypatch.setattr(
        monte_carlo_mode,
        'store_session_exception',
        lambda value, session_type, error, traceback: exceptions.append(
            (value, session_type, error, traceback)
        ),
    )

    with pytest.raises(RuntimeError, match='validation failed'):
        monte_carlo_mode.run(
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
            run_trades=True,
            run_candles=False,
            num_scenarios=10,
            fast_mode=True,
            cpu_cores=1,
            pipeline_type=None,
            pipeline_params=None,
            state={},
        )

    assert status_updates == [(session_id, 'stopped')]
    assert len(exceptions) == 1
    assert exceptions[0][0:3] == ('trades-id', 'trades', 'RuntimeError: validation failed')
    assert 'RuntimeError: validation failed' in exceptions[0][3]


def test_monte_carlo_controller_persists_session_before_worker_start(monkeypatch):
    session_id = '5a621676-102d-4f3f-ac73-7801a622fdab'
    events = []
    request = SimpleNamespace(
        id=session_id,
        config={},
        exchange='Sandbox',
        routes=[{'symbol': 'BTC-USDT'}],
        data_routes=[],
        start_date='2025-01-01',
        finish_date='2025-02-01',
        run_trades=True,
        run_candles=False,
        num_scenarios=10,
        fast_mode=True,
        cpu_cores=1,
        pipeline_type=None,
        pipeline_params=None,
        state={'form': {'id': session_id}},
    )

    monkeypatch.setattr(monte_carlo_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(
        monte_carlo_controller,
        'get_monte_carlo_session_by_id',
        lambda value: None,
    )
    monkeypatch.setattr(
        monte_carlo_controller,
        'store_monte_carlo_session',
        lambda **kwargs: events.append(('store', kwargs)),
    )
    monkeypatch.setattr(
        monte_carlo_controller.process_manager,
        'add_task',
        lambda *args: events.append(('worker', args[1])),
    )

    asyncio.run(monte_carlo_controller.monte_carlo(None, request))

    assert [event[0] for event in events] == ['store', 'worker']
