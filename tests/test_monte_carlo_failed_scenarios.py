from importlib import import_module

from jesse.research.monte_carlo import common

# the package re-exports the class under the module's name
runner_module = import_module('jesse.modes.monte_carlo_mode.MonteCarloRunner')


def _fake_ray(monkeypatch, responses: list) -> list:
    refs = list(range(len(responses)))
    monkeypatch.setattr(common.ray, 'wait', lambda remaining, num_returns, timeout: (remaining[:1], remaining[1:]))
    monkeypatch.setattr(common.ray, 'get', lambda ref: responses[ref])
    return refs


def test_failed_scenarios_reach_the_callers_log(monkeypatch):
    refs = _fake_ray(monkeypatch, [
        {'result': {'scenario_index': 1}, 'log': None, 'error': False},
        {'result': None, 'log': 'Scenario 2 failed with ValueError: overflow\nTraceback ...', 'error': True},
        {'result': {'scenario_index': 3}, 'log': 'Info: Scenario 3 missing equity_curve', 'error': False},
    ])
    logged = []

    results = common._process_scenario_results(refs, None, log_callback=lambda message, is_error: logged.append((message, is_error)))

    assert [r['scenario_index'] for r in results] == [1, 3]
    assert logged == [
        ('Scenario 2 failed with ValueError: overflow\nTraceback ...', True),
        ('Info: Scenario 3 missing equity_curve', False),
    ]


def test_without_a_callback_errors_still_go_to_the_monte_carlo_session_log(monkeypatch):
    refs = _fake_ray(monkeypatch, [{'result': None, 'log': 'Scenario 1 failed', 'error': True}])
    written = []
    monkeypatch.setattr(common.jh, 'app_mode', lambda: 'monte-carlo')
    monkeypatch.setattr(common.jh, 'get_session_id', lambda: 'session')
    monkeypatch.setattr(common.logger, 'log_monte_carlo', lambda message, session_id: written.append((message, session_id)))

    assert common._process_scenario_results(refs, None) == []
    assert written == [('ERROR: Scenario 1 failed', 'session')]


def test_the_runner_logs_every_failure_to_its_session(monkeypatch):
    written = []
    monkeypatch.setattr(runner_module.logger, 'log_monte_carlo', lambda message, session_id: written.append(message))
    monkeypatch.setattr(runner_module, 'sync_publish', lambda *args, **kwargs: None)

    def fake_monte_carlo_candles(**kwargs):
        for i in range(1, 6):
            kwargs['log_callback'](f'Scenario {i} failed with ValueError: overflow\nTraceback line', True)
        return {'scenarios': [], 'num_scenarios': 0, 'total_requested': 5, 'failed_scenarios': 5, 'filtered_scenarios': 0}

    monkeypatch.setattr(runner_module, 'monte_carlo_candles', fake_monte_carlo_candles)
    runner = runner_module.MonteCarloRunner.__new__(runner_module.MonteCarloRunner)
    runner.session_id = 'session'
    runner.num_scenarios = 5
    runner.candles = {}
    runner.routes = runner.data_routes = []
    runner.warmup_candles = None
    runner.fast_mode = True
    runner.cpu_cores = 1
    runner._raise_if_cancelled = lambda: None

    runner._run_candles_with_progress({}, None, {})

    errors = [m for m in written if m.startswith('ERROR: ')]
    assert len(errors) == 5
    # full tracebacks for the first few, a single line after that
    assert ['\n' in m for m in errors] == [True] * runner_module.MAX_FULL_SCENARIO_TRACEBACKS + [False] * 2
