from importlib import import_module
import threading
from types import SimpleNamespace

import pytest

from jesse import exceptions


multiprocessing_service = import_module('jesse.services.multiprocessing')
significance_package = import_module('jesse.research.rule_significance_testing')
significance_runner_module = import_module(
    'jesse.modes.significance_test_mode.SignificanceTestRunner'
)
significance_mode = import_module('jesse.modes.significance_test_mode')
monte_carlo_runner_module = import_module(
    'jesse.modes.monte_carlo_mode.MonteCarloRunner'
)
monte_carlo_mode = import_module('jesse.modes.monte_carlo_mode')
optimizer_module = import_module('jesse.modes.optimize_mode.Optimize')
optimize_mode = import_module('jesse.modes.optimize_mode')


def test_process_marker_exists_before_worker_starts(monkeypatch):
    """A child must never mistake its startup race for a cancellation request."""
    events = []

    class FakeProcess:
        def __init__(self, target, args):
            self.pid = 123

        def start(self):
            events.append('start')

    manager = multiprocessing_service.ProcessManager.__new__(
        multiprocessing_service.ProcessManager
    )
    manager._workers = []
    manager._pid_to_client_id_map = {}
    manager.client_id_to_pid_to_map = {}
    manager._pending_worker_removals = set()
    manager._workers_lock = threading.Lock()
    manager._shutting_down = False
    manager._add_process = lambda client_id: events.append(('active', client_id))

    monkeypatch.setattr(multiprocessing_service, 'Process', FakeProcess)
    monkeypatch.setitem(multiprocessing_service.ENV_VALUES, 'APP_PORT', '9000')

    manager.add_task(lambda: None, 'session-id')

    assert events == [('active', 'session-id'), 'start']


def test_process_start_failure_removes_active_marker(monkeypatch):
    """A process that never starts must not remain cancellable in coordinator."""
    removals = []

    class FailingProcess:
        def __init__(self, target, args):
            self.pid = None

        def start(self):
            raise RuntimeError('process failed to start')

    manager = multiprocessing_service.ProcessManager.__new__(
        multiprocessing_service.ProcessManager
    )
    manager._workers = []
    manager._pid_to_client_id_map = {}
    manager.client_id_to_pid_to_map = {}
    manager._pending_worker_removals = set()
    manager._workers_lock = threading.Lock()
    manager._shutting_down = False
    manager._add_process = lambda client_id: None
    manager._remove_active_worker = lambda client_id: removals.append(client_id)

    monkeypatch.setattr(multiprocessing_service, 'Process', FailingProcess)

    with pytest.raises(RuntimeError, match='process failed to start'):
        manager.add_task(lambda: None, 'session-id')

    assert manager._workers == []
    assert removals == ['session-id']


def test_marker_publish_failure_leaves_no_unstarted_worker(monkeypatch):
    """A coordinator failure publishing the marker leaves no never-started Process in _workers."""
    removals = []
    started = []

    class RecordingProcess:
        def __init__(self, target, args):
            self.pid = None

        def start(self):
            started.append(True)

    def unreachable(client_id):
        raise ConnectionError('coordinator unreachable')

    manager = multiprocessing_service.ProcessManager.__new__(
        multiprocessing_service.ProcessManager
    )
    manager._workers = []
    manager._pid_to_client_id_map = {}
    manager.client_id_to_pid_to_map = {}
    manager._pending_worker_removals = set()
    manager._workers_lock = threading.Lock()
    manager._shutting_down = False
    manager._add_process = unreachable
    manager._remove_active_worker = lambda client_id: removals.append(client_id)

    monkeypatch.setattr(multiprocessing_service, 'Process', RecordingProcess)

    with pytest.raises(ConnectionError, match='coordinator unreachable'):
        manager.add_task(lambda: None, 'session-id')

    assert manager._workers == [] and started == []
    assert removals == ['session-id']


def test_shutdown_refuses_a_late_worker_launch(monkeypatch):
    """An accepted request cannot escape shutdown by spawning after the snapshot."""
    manager = multiprocessing_service.ProcessManager.__new__(multiprocessing_service.ProcessManager)
    manager._workers_lock = threading.Lock()
    manager._shutting_down = True
    manager._workers = []

    def unexpected_process(**kwargs):
        raise AssertionError('Shutdown must refuse the launch before constructing a worker')

    monkeypatch.setattr(multiprocessing_service, 'Process', unexpected_process)
    with pytest.raises(RuntimeError, match='shutting down'):
        manager.add_task(lambda: None, 'synthetic-session')
    assert manager._workers == []


def _significance_runner(monkeypatch, active=True):
    monkeypatch.setattr(significance_runner_module.jh, 'get_session_id', lambda: 'session-id')
    monkeypatch.setattr(significance_runner_module, 'is_process_active', lambda value: active)
    return significance_runner_module.SignificanceTestRunner(
        session_id='session-id',
        user_config={'warm_up_candles': 0},
        routes=[{'exchange': 'Sandbox'}],
        data_routes=[],
        candles={},
        warmup_candles={},
        n_simulations=10,
        random_seed=7,
        theme='light',
    )


def test_significance_runner_persists_results_before_finishing(monkeypatch):
    events = []
    runner = _significance_runner(monkeypatch)
    result = {
        'observed_mean': 0.01,
        'annualized_return': 3.65,
        'p_value': 0.02,
        'n_simulations': 10,
        'n_observations': 100,
        'simulated_means': [],
    }

    def run_significance_test(**kwargs):
        kwargs['progress_callback'](100, 100)
        return result

    monkeypatch.setattr(significance_package, 'rule_significance_test', run_significance_test)
    monkeypatch.setattr(significance_package, 'plot_significance_test', lambda **kwargs: '/tmp/chart.png')
    monkeypatch.setattr(
        significance_runner_module,
        'update_significance_test_session_results',
        lambda **kwargs: events.append(('results', kwargs)),
    )
    monkeypatch.setattr(
        significance_runner_module,
        'update_significance_test_session_status',
        lambda session_id, status: events.append(('status', status)),
    )
    monkeypatch.setattr(
        significance_runner_module,
        'sync_publish',
        lambda event, payload: events.append(('publish', event, payload)),
    )

    runner.run()

    assert events.index(next(event for event in events if event[0] == 'results')) < events.index(
        ('status', 'finished')
    )
    saved = next(event[1] for event in events if event[0] == 'results')
    assert saved['results'] == {
        'observed_mean': 0.01,
        'annualized_return': 3.65,
        'p_value': 0.02,
        'n_simulations': 10,
        'n_observations': 100,
    }
    assert saved['chart_path'] == '/tmp/chart.png'


def test_significance_runner_persists_one_typed_failure(monkeypatch):
    errors = []
    statuses = []
    runner = _significance_runner(monkeypatch)
    monkeypatch.setattr(
        runner,
        '_run_significance_test',
        lambda: (_ for _ in ()).throw(RuntimeError('intentional runner failure')),
    )
    monkeypatch.setattr(
        significance_runner_module,
        'store_significance_test_exception',
        lambda session_id, error, traceback: errors.append((error, traceback)),
    )
    monkeypatch.setattr(
        significance_runner_module,
        'update_significance_test_session_status',
        lambda session_id, status: statuses.append(status),
    )
    monkeypatch.setattr(significance_runner_module, 'sync_publish', lambda *args: None)

    with pytest.raises(RuntimeError, match='intentional runner failure'):
        runner.run()

    assert statuses == ['stopped']
    assert len(errors) == 1
    assert errors[0][0] == 'RuntimeError: intentional runner failure'
    assert errors[0][0] in errors[0][1]


@pytest.mark.parametrize(('stored_status', 'expected_updates'), [('running', ['stopped']), ('terminated', [])])
def test_significance_cancellation_preserves_explicit_termination(
    monkeypatch,
    stored_status,
    expected_updates,
):
    runner = _significance_runner(monkeypatch, active=False)
    updates = []
    monkeypatch.setattr(
        significance_runner_module,
        'get_significance_test_session_by_id',
        lambda session_id: SimpleNamespace(status=stored_status),
    )
    monkeypatch.setattr(
        significance_runner_module,
        'update_significance_test_session_status',
        lambda session_id, status: updates.append(status),
    )

    with pytest.raises(exceptions.Termination):
        runner.run()

    assert updates == expected_updates


def _monte_carlo_runner(monkeypatch):
    monkeypatch.setattr(monte_carlo_runner_module.jh, 'get_session_id', lambda: 'session-id')
    monkeypatch.setattr(monte_carlo_runner_module, 'is_process_active', lambda value: True)
    monkeypatch.setattr(monte_carlo_runner_module.ray, 'is_initialized', lambda: False)
    monkeypatch.setattr(monte_carlo_runner_module.ray, 'init', lambda **kwargs: None)
    monkeypatch.setattr(monte_carlo_runner_module.ray, 'shutdown', lambda: None)
    monkeypatch.setattr(monte_carlo_runner_module.logger, 'log_monte_carlo', lambda *args, **kwargs: None)
    return monte_carlo_runner_module.MonteCarloRunner(
        session_id='session-id',
        user_config={'exchange': {'type': 'futures'}},
        routes=[{'exchange': 'Sandbox'}],
        data_routes=[],
        candles={},
        warmup_candles={},
        run_trades=True,
        run_candles=False,
        num_scenarios=2,
        fast_mode=True,
        cpu_cores=1,
        pipeline_type=None,
        pipeline_params=None,
    )


def test_monte_carlo_runner_persists_child_results_before_parent_finishes(monkeypatch):
    events = []
    runner = _monte_carlo_runner(monkeypatch)
    results = {'num_scenarios': 2, 'confidence_analysis': {}}
    monkeypatch.setattr(runner, '_run_trades_with_progress', lambda config: results)
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'store_trades_session',
        lambda **kwargs: 'trades-id',
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'update_trades_session_progress',
        lambda **kwargs: events.append(('results', kwargs)),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'update_trades_session_status',
        lambda session_id, status: events.append(('child-status', status)),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'update_monte_carlo_session_status',
        lambda session_id, status: events.append(('parent-status', status)),
    )
    monkeypatch.setattr(monte_carlo_runner_module, 'append_session_logs', lambda *args: None)
    monkeypatch.setattr(monte_carlo_runner_module, 'sync_publish', lambda *args: None)

    runner.run()

    assert events == [
        ('results', {'id': 'trades-id', 'completed': 2, 'results': results}),
        ('child-status', 'finished'),
        ('parent-status', 'finished'),
    ]


def test_monte_carlo_runner_persists_child_failure_once(monkeypatch):
    failures = []
    child_statuses = []
    parent_statuses = []
    runner = _monte_carlo_runner(monkeypatch)
    monkeypatch.setattr(
        runner,
        '_run_trades_with_progress',
        lambda config: (_ for _ in ()).throw(RuntimeError('intentional Monte Carlo failure')),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'store_trades_session',
        lambda **kwargs: 'trades-id',
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'store_session_exception',
        lambda *args: failures.append(args),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'update_trades_session_status',
        lambda session_id, status: child_statuses.append(status),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'update_monte_carlo_session_status',
        lambda session_id, status: parent_statuses.append(status),
    )
    monkeypatch.setattr(monte_carlo_runner_module, 'sync_publish', lambda *args: None)

    with pytest.raises(RuntimeError, match='intentional Monte Carlo failure'):
        runner.run()

    assert len(failures) == 1
    assert failures[0][0:3] == (
        'trades-id',
        'trades',
        'RuntimeError: intentional Monte Carlo failure',
    )
    assert child_statuses == ['stopped']
    assert parent_statuses == ['stopped']


def test_monte_carlo_cancellation_stops_child_without_persisting_failure(monkeypatch):
    failures = []
    child_statuses = []
    parent_statuses = []
    runner = _monte_carlo_runner(monkeypatch)
    monkeypatch.setattr(
        runner,
        '_run_trades_with_progress',
        lambda config: (_ for _ in ()).throw(exceptions.Termination()),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'store_trades_session',
        lambda **kwargs: 'trades-id',
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'store_session_exception',
        lambda *args: failures.append(args),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'update_trades_session_status',
        lambda session_id, status: child_statuses.append(status),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'get_monte_carlo_session_by_id',
        lambda session_id: SimpleNamespace(status='terminated'),
    )
    monkeypatch.setattr(
        monte_carlo_runner_module,
        'update_monte_carlo_session_status',
        lambda session_id, status: parent_statuses.append(status),
    )
    monkeypatch.setattr(monte_carlo_runner_module, 'sync_publish', lambda *args: None)

    with pytest.raises(exceptions.Termination):
        runner.run()

    assert failures == []
    assert child_statuses == ['stopped']
    assert parent_statuses == []


class FakeStudy:
    trials = []
    best_trial = 'best-trial'


def _optimizer(monkeypatch):
    optimizer = optimizer_module.Optimizer.__new__(optimizer_module.Optimizer)
    optimizer.session_id = 'session-id'
    optimizer.cpu_cores = 1
    optimizer.completed_trials = 0
    optimizer.trial_counter = 0
    optimizer.n_trials = 1
    optimizer.study = FakeStudy()
    optimizer.user_config = {}
    optimizer.strategy_hp = []
    optimizer.training_warmup_candles = {}
    optimizer.training_candles = {}
    optimizer.testing_warmup_candles = {}
    optimizer.testing_candles = {}
    optimizer.optimal_total = 1
    optimizer.fast_mode = True
    optimizer.objective_function = 'sharpe'
    optimizer.best_trials = []
    optimizer.client_id = 'session-id'
    optimizer.ray_started_here = True
    optimizer._generate_trial_params = lambda: {}

    monkeypatch.setattr(optimizer_module, 'is_process_active', lambda value: True)
    monkeypatch.setattr(optimizer_module, 'router', SimpleNamespace(formatted_routes=[], formatted_data_routes=[]))
    monkeypatch.setattr(optimizer_module.ray, 'put', lambda value: value)
    monkeypatch.setattr(optimizer_module.ray, 'is_initialized', lambda: True)
    monkeypatch.setattr(optimizer_module.logger, 'log_optimize_mode', lambda *args: None)
    monkeypatch.setattr(optimizer_module, 'sync_publish', lambda *args: None)
    return optimizer


def test_optimizer_persists_final_trials_and_cleans_owned_ray(monkeypatch):
    events = []
    optimizer = _optimizer(monkeypatch)

    class FakeRemote:
        def options(self, **kwargs):
            return self

        def remote(self, *args):
            return 'trial-ref'

    monkeypatch.setattr(optimizer_module, 'ray_evaluate_trial', FakeRemote())
    monkeypatch.setattr(optimizer_module.ray, 'wait', lambda refs, **kwargs: (['trial-ref'], []))
    monkeypatch.setattr(
        optimizer_module.ray,
        'get',
        lambda ref: {
            'trial_number': 0,
            'score': 1.0,
            'params': {},
            'training_metrics': {},
            'testing_metrics': {},
        },
    )
    monkeypatch.setattr(optimizer_module.ray, 'shutdown', lambda: events.append(('ray', 'shutdown')))
    monkeypatch.setattr(optimizer_module.ray, 'cancel', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        optimizer_module,
        'update_optimization_session_trials',
        lambda session_id, completed, best, total: events.append(
            ('trials', completed, best, total)
        ),
    )
    monkeypatch.setattr(
        optimizer_module,
        'update_optimization_session_status',
        lambda session_id, status: events.append(('status', status)),
    )

    def process_result(result):
        optimizer.completed_trials = 1
        optimizer.best_trials = [{'trial': 0}]

    optimizer._process_trial_result = process_result

    result = optimizer.run()

    assert result == 'best-trial'
    assert ('trials', 1, [{'trial': 0}], 1) in events
    assert events.index(('trials', 1, [{'trial': 0}], 1)) < events.index(
        ('status', 'finished')
    )
    assert events[-1] == ('ray', 'shutdown')


def test_optimizer_failure_is_persisted_once_and_cancels_only_its_work(monkeypatch):
    failures = []
    events = []
    optimizer = _optimizer(monkeypatch)

    class FakeRemote:
        def options(self, **kwargs):
            return self

        def remote(self, *args):
            return 'trial-ref'

    monkeypatch.setattr(optimizer_module, 'ray_evaluate_trial', FakeRemote())
    monkeypatch.setattr(
        optimizer_module.ray,
        'wait',
        lambda refs, **kwargs: (_ for _ in ()).throw(RuntimeError('intentional optimizer failure')),
    )
    monkeypatch.setattr(
        optimizer_module.ray,
        'cancel',
        lambda ref, force: events.append(('cancel', ref, force)),
    )
    monkeypatch.setattr(optimizer_module.ray, 'shutdown', lambda: events.append(('ray', 'shutdown')))
    monkeypatch.setattr(
        optimizer_module,
        'update_optimization_session_trials',
        lambda *args: None,
    )
    monkeypatch.setattr(
        optimizer_module,
        'update_optimization_session_status',
        lambda session_id, status: events.append(('status', status)),
    )
    optimization_model = import_module('jesse.models.OptimizationSession')
    monkeypatch.setattr(
        optimization_model,
        'add_session_exception',
        lambda session_id, error, traceback: failures.append((error, traceback)),
    )

    with pytest.raises(RuntimeError, match='intentional optimizer failure'):
        optimizer.run()

    assert len(failures) == 1
    assert failures[0][0] == 'RuntimeError: intentional optimizer failure'
    assert failures[0][0] in failures[0][1]
    assert ('cancel', 'trial-ref', True) in events
    assert events[-1] == ('ray', 'shutdown')


def test_significance_mode_does_not_duplicate_runner_failure(monkeypatch):
    failures = []
    resets = []

    class FailingRunner:
        def __init__(self, **kwargs):
            pass

        def run(self):
            failures.append('runner')
            raise RuntimeError('runner owns this failure')

    monkeypatch.setattr('jesse.config.set_config', lambda config: None)
    monkeypatch.setattr(significance_mode.router, 'initiate', lambda routes, data_routes: None)
    monkeypatch.setattr(significance_mode.router, 'routes', [])
    monkeypatch.setattr(significance_mode.store.app, 'set_session_id', lambda value: None)
    monkeypatch.setattr(significance_mode, 'register_custom_exception_handler', lambda: None)
    monkeypatch.setattr(significance_mode, 'validate_routes', lambda value: None)
    monkeypatch.setattr(significance_mode, 'load_candles', lambda start, finish: ({}, {}))
    monkeypatch.setattr(significance_mode, 'SignificanceTestRunner', FailingRunner)
    monkeypatch.setattr(
        significance_mode,
        'store_significance_test_exception',
        lambda *args: failures.append('outer'),
    )
    monkeypatch.setattr(
        significance_mode,
        'update_significance_test_session_status',
        lambda *args: None,
    )
    monkeypatch.setattr(
        significance_mode,
        'update_significance_test_session_state',
        lambda *args: None,
    )
    monkeypatch.setattr(
        significance_mode,
        '_reset_research_runtime_state',
        lambda: resets.append('reset'),
    )

    with pytest.raises(RuntimeError, match='runner owns this failure'):
        significance_mode.run(
            session_id='session-id',
            user_config={},
            exchange='Sandbox',
            routes=[{'symbol': 'BTC-USDT'}],
            data_routes=[],
            start_date='2025-01-01',
            finish_date='2025-02-01',
            n_simulations=10,
            random_seed=7,
            theme='light',
            state={},
        )

    assert failures == ['runner']
    assert resets == ['reset']


def test_monte_carlo_mode_does_not_duplicate_runner_failure(monkeypatch):
    failures = []
    resets = []

    class FailingRunner:
        def __init__(self, **kwargs):
            pass

        def run(self):
            failures.append('runner')
            raise RuntimeError('runner owns this failure')

    monkeypatch.setattr('jesse.config.set_config', lambda config: None)
    monkeypatch.setattr(monte_carlo_mode.router, 'initiate', lambda routes, data_routes: None)
    monkeypatch.setattr(monte_carlo_mode.router, 'routes', [])
    monkeypatch.setattr(monte_carlo_mode.store.app, 'set_session_id', lambda value: None)
    monkeypatch.setattr(monte_carlo_mode, 'register_custom_exception_handler', lambda: None)
    monkeypatch.setattr(monte_carlo_mode, 'validate_routes', lambda value: None)
    monkeypatch.setattr(monte_carlo_mode, 'load_candles', lambda start, finish: ({}, {}))
    monkeypatch.setattr(monte_carlo_mode, 'MonteCarloRunner', FailingRunner)
    monkeypatch.setattr(
        monte_carlo_mode,
        'get_monte_carlo_session_by_id',
        lambda session_id: SimpleNamespace(status='running'),
    )
    monkeypatch.setattr(
        monte_carlo_mode,
        'update_monte_carlo_session_status',
        lambda *args: None,
    )
    monkeypatch.setattr(
        monte_carlo_mode,
        'update_monte_carlo_session_state',
        lambda *args: None,
    )
    monkeypatch.setattr(
        monte_carlo_mode,
        'store_session_exception',
        lambda *args: failures.append('outer'),
    )
    monkeypatch.setattr(
        monte_carlo_mode,
        '_reset_research_runtime_state',
        lambda: resets.append('reset'),
    )

    with pytest.raises(RuntimeError, match='runner owns this failure'):
        monte_carlo_mode.run(
            session_id='session-id',
            user_config={},
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
            state={},
        )

    assert failures == ['runner']
    assert resets == ['reset']


def test_optimize_mode_does_not_duplicate_optimizer_failure(monkeypatch):
    failures = []
    resets = []

    class FailingOptimizer:
        def __init__(self, *args):
            pass

        def run(self):
            failures.append('optimizer')
            raise RuntimeError('optimizer owns this failure')

    monkeypatch.setattr('jesse.config.set_config', lambda config: None)
    monkeypatch.setattr(optimize_mode.router, 'initiate', lambda routes, data_routes: None)
    monkeypatch.setattr(optimize_mode.router, 'routes', [])
    monkeypatch.setattr(optimize_mode.store.app, 'set_session_id', lambda value: None)
    monkeypatch.setattr(optimize_mode, 'register_custom_exception_handler', lambda: None)
    monkeypatch.setattr(optimize_mode, 'validate_routes', lambda value: None)
    monkeypatch.setattr(
        optimize_mode,
        '_get_training_and_testing_candles',
        lambda *args: ({}, {}, {}, {}),
    )
    monkeypatch.setattr(optimize_mode, 'Optimizer', FailingOptimizer)
    monkeypatch.setattr(
        optimize_mode,
        'get_optimization_session_by_id',
        lambda session_id: SimpleNamespace(status='running'),
    )
    monkeypatch.setattr(
        optimize_mode,
        'update_optimization_session_status',
        lambda *args: None,
    )
    monkeypatch.setattr(
        optimize_mode,
        'update_optimization_session_state',
        lambda *args: None,
    )
    optimization_model = import_module('jesse.models.OptimizationSession')
    monkeypatch.setattr(
        optimization_model,
        'add_session_exception',
        lambda *args: failures.append('outer'),
    )
    monkeypatch.setattr(
        optimize_mode,
        '_reset_research_runtime_state',
        lambda: resets.append('reset'),
    )

    with pytest.raises(RuntimeError, match='optimizer owns this failure'):
        optimize_mode.run(
            session_id='session-id',
            user_config={},
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
            state={},
        )

    assert failures == ['optimizer']
    assert resets == ['reset']
