"""Research runners: code bundles, the job queue (on a real PostgreSQL), fencing and the worker entry."""
import json
import os
import sys
import threading
import time
import uuid
from types import SimpleNamespace

import peewee
import pytest

from jesse.models.BacktestSession import BacktestSession, update_backtest_session_status
from jesse.models.MonteCarloSession import MonteCarloCandlesSession, MonteCarloSession, MonteCarloTradesSession
from jesse.models.OptimizationSession import OptimizationSession, get_optimization_session_by_id
from jesse.models.RunnerJob import CodeBlob, Runner, RunnerFile, RunnerJob
from jesse.models.SignificanceTestSession import SignificanceTestSession
from jesse.services import code_bundle, runner_queue, runner_worker, session_liveness
from jesse.services import redis as coordinator

SESSION_MODELS = [BacktestSession, OptimizationSession, MonteCarloSession, MonteCarloTradesSession,
                  MonteCarloCandlesSession, SignificanceTestSession]
QUEUE_MODELS = [RunnerJob, Runner, CodeBlob, RunnerFile]


def _write(root, relative, text):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Code bundles
# ---------------------------------------------------------------------------

@pytest.fixture
def project(tmp_path):
    root = str(tmp_path)
    _write(root, 'strategies/Base/__init__.py', 'import numpy as np\nfrom custom_indicators.trend import slope\n')
    _write(root, 'strategies/Base/params.json', '{"fast": 9}')
    _write(root, 'strategies/Variant7/__init__.py',
           'import json, os\nfrom jesse.strategies import Strategy\nfrom strategies.Base import *\nimport talib\n')
    _write(root, 'strategies/PairA/__init__.py', 'from strategies import Shared\nimport pandas as pd\n')
    _write(root, 'strategies/PairB/__init__.py', 'from . import helpers\n')
    _write(root, 'strategies/PairB/helpers.py', 'X = 1\n')
    _write(root, 'strategies/Shared/__init__.py', 'import math\n')
    _write(root, 'strategies/Unrelated/__init__.py', 'raise SystemExit\n')
    _write(root, 'custom_indicators/__init__.py', '')
    _write(root, 'custom_indicators/trend.py', 'from .core import base\n')
    _write(root, 'custom_indicators/core.py', 'base = 1\n')
    _write(root, 'storage/logs/x.txt', 'not code')
    os.makedirs(os.path.join(root, 'strategies/Base/__pycache__'))
    _write(root, 'strategies/Base/__pycache__/x.cpython-312.pyc', 'junk')
    return root


def test_a_bundle_follows_strategy_and_project_imports(project):
    bundle = code_bundle.build(['Variant7'], project)

    assert sorted(bundle['files']) == [
        'custom_indicators/__init__.py', 'custom_indicators/core.py', 'custom_indicators/trend.py',
        'strategies/Base/__init__.py', 'strategies/Base/params.json', 'strategies/Variant7/__init__.py',
    ]
    assert bundle['packages'] == ['numpy', 'talib']


def test_a_pairs_bundle_carries_every_routes_strategy_and_their_helpers(project):
    bundle = code_bundle.build(['PairA', 'PairB', 'PairA'], project)

    assert sorted(bundle['files']) == [
        'strategies/PairA/__init__.py', 'strategies/PairB/__init__.py', 'strategies/PairB/helpers.py',
        'strategies/Shared/__init__.py',
    ]
    assert bundle['packages'] == ['pandas']


def test_a_missing_strategy_a_syntax_error_and_an_oversized_bundle_are_refused(project, monkeypatch):
    with pytest.raises(code_bundle.BundleError, match='"Nope" was not found'):
        code_bundle.build(['Nope'], project)

    _write(project, 'strategies/Broken/__init__.py', 'def oops(:\n')
    with pytest.raises(code_bundle.BundleError, match='syntax error'):
        code_bundle.build(['Broken'], project)

    monkeypatch.setattr(code_bundle, 'MAX_BUNDLE_BYTES', 10)
    with pytest.raises(code_bundle.BundleError, match='above the 0 MB limit'):
        code_bundle.build(['Variant7'], project)


@pytest.fixture
def sqlite_queue_db():
    database = peewee.SqliteDatabase(':memory:')
    with database.bind_ctx(QUEUE_MODELS + SESSION_MODELS):
        database.create_tables(QUEUE_MODELS + SESSION_MODELS)
        yield database


def test_files_are_stored_once_and_restored_byte_for_byte(project, tmp_path, sqlite_queue_db):
    first = code_bundle.store(code_bundle.build(['Variant7'], project), now_ms=1)
    second = code_bundle.store(code_bundle.build(['Variant7', 'PairA'], project), now_ms=2)

    assert set(first.items()) <= set(second.items())
    assert CodeBlob.select().count() == len(set(second.values()))
    assert CodeBlob.get(CodeBlob.hash == first['strategies/Base/params.json']).last_used_at == 2

    destination = str(tmp_path / 'job')
    code_bundle.materialize(second, destination, str(tmp_path / 'cache'))
    with open(os.path.join(destination, 'strategies/Base/params.json')) as f:
        assert f.read() == '{"fast": 9}'
    assert os.path.exists(os.path.join(destination, 'custom_indicators/core.py'))

    # A second job reuses the local copies without reading the database.
    CodeBlob.delete().execute()
    code_bundle.materialize(first, str(tmp_path / 'job2'), str(tmp_path / 'cache'))
    assert os.path.exists(os.path.join(tmp_path, 'job2/strategies/Variant7/__init__.py'))


# ---------------------------------------------------------------------------
# The worker entry point
# ---------------------------------------------------------------------------

def test_a_runner_worker_runs_the_jobs_own_code_in_the_job_folder(tmp_path, monkeypatch):
    job_dir = str(tmp_path / 'job')
    _write(job_dir, 'strategies/Probe/__init__.py', 'WHERE = "bundle"\n')
    os.makedirs(os.path.join(job_dir, 'storage'))
    seen = {}

    def fake_run(session_id, value):
        import importlib
        seen['module'] = importlib.import_module('strategies.Probe').WHERE
        seen['cwd'] = os.getcwd()
        seen['value'] = value
        seen['claim'] = session_liveness._claim_id

    sys.modules['strategies'] = SimpleNamespace(__name__='strategies-from-runner-project')
    monkeypatch.setattr(runner_worker, '_mode_function', lambda function: fake_run)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setenv('PYTHONPATH', '')
    try:
        runner_worker.run_queued_job('sid-1', 'backtest', json.dumps(['sid-1', 42]), job_dir, 'claim-1')
    finally:
        session_liveness.set_claim(None)
        for name in [n for n in sys.modules if n == 'strategies' or n.startswith('strategies.')]:
            del sys.modules[name]

    assert seen == {'module': 'bundle', 'cwd': os.path.realpath(job_dir), 'value': 42, 'claim': 'claim-1'}
    assert os.environ['PYTHONPATH'].split(os.pathsep)[0] == job_dir

    with pytest.raises(ValueError, match='do not belong'):
        runner_worker.run_queued_job('sid-1', 'backtest', json.dumps(['other', 1]), job_dir, 'c')
    session_liveness.set_claim(None)


# ---------------------------------------------------------------------------
# The queue, on a real PostgreSQL in a throwaway schema
# ---------------------------------------------------------------------------

def _postgres():
    env_path = os.environ.get('JESSE_TEST_POSTGRES_ENV')
    if not env_path or not os.path.exists(env_path):
        return None
    import re
    values = dict(re.findall(r'^(\w+)=(.*)$', open(env_path).read(), re.M))
    return {key: values[key].strip().strip('"\'') for key in
            ('POSTGRES_NAME', 'POSTGRES_USERNAME', 'POSTGRES_PASSWORD', 'POSTGRES_HOST', 'POSTGRES_PORT')}


@pytest.fixture
def pg(monkeypatch):
    config = _postgres()
    if config is None:
        pytest.skip('Set JESSE_TEST_POSTGRES_ENV to a .env with PostgreSQL credentials to run the queue tests.')
    schema = f'runner_test_{uuid.uuid4().hex[:8]}'
    database = peewee.PostgresqlDatabase(
        config['POSTGRES_NAME'], user=config['POSTGRES_USERNAME'], password=config['POSTGRES_PASSWORD'],
        host=config['POSTGRES_HOST'], port=int(config['POSTGRES_PORT']), options=f'-c search_path={schema}')
    database.execute_sql(f'CREATE SCHEMA {schema}')
    from jesse.services import db as db_module
    monkeypatch.setattr(db_module.database, 'db', database)
    monkeypatch.setattr(session_liveness, 'jh', SimpleNamespace(is_unit_testing=lambda: False))
    monkeypatch.setattr(runner_queue, 'jh', SimpleNamespace(is_unit_testing=lambda: False))
    monkeypatch.setattr(session_liveness, '_label', 'hub:9001')
    monkeypatch.setattr(session_liveness, '_claim_id', None)
    monkeypatch.setattr(coordinator, 'is_process_active', lambda client_id: False)
    monkeypatch.setitem(runner_queue.ENV_VALUES, 'RESEARCH_RUNNERS', 'true')
    # _enqueue changes into the project folder; later tests must not run from there.
    monkeypatch.chdir(os.getcwd())
    try:
        with database.bind_ctx(QUEUE_MODELS + SESSION_MODELS):
            database.create_tables(QUEUE_MODELS + SESSION_MODELS)
            yield database
    finally:
        database.execute_sql(f'DROP SCHEMA {schema} CASCADE')
        database.close()


def _now():
    return session_liveness.now_ms()


def _backtest(status='draft'):
    session_id = str(uuid.uuid4())
    BacktestSession.insert(id=session_id, status=status, created_at=_now(), updated_at=_now()).execute()
    return session_id


def _runner(name, version=None, seconds_ago=0):
    Runner.insert(name=name, host=name, cores_budget=8, cores_used=0, cpu_cores=8,
                  jesse_version=version or runner_queue.jesse_version(), started_at=_now(),
                  last_seen=_now() - seconds_ago * 1000).execute()


def _claim(name):
    """claim_next with the runner's budget and free cores from its row (8 of 8 for an unknown runner)."""
    row = Runner.get_or_none(Runner.name == name)
    budget = row.cores_budget if row else 8
    return runner_queue.claim_next(name, budget - (row.cores_used if row else 0), budget)


def _enqueue(project, session_id, target=None, strategy='Variant7'):
    os.chdir(project)
    return runner_queue.enqueue('backtest', 'backtest', [session_id, False, {}], [strategy], target)


def _session(session_id):
    return BacktestSession.get(BacktestSession.id == session_id)


def test_queuing_marks_the_session_queued_and_stores_the_call(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    session_id = _backtest()

    job_id = _enqueue(project, session_id)

    job = RunnerJob.get(RunnerJob.id == job_id)
    assert (job.status, job.function, job.target, job.attempt) == ('queued', 'backtest', None, 0)
    assert json.loads(job.arguments) == [session_id, False, {}]
    assert 'strategies/Base/params.json' in json.loads(job.code_manifest)
    assert json.loads(job.packages) == ['numpy', 'talib']
    assert _session(session_id).status == 'queued'


def test_where_resolves_to_local_unless_runners_are_on(pg, monkeypatch):
    assert runner_queue.resolve_target(None) == ('local', None)
    assert runner_queue.resolve_target('local') == ('local', None)
    assert runner_queue.resolve_target('auto') == ('local', None)  # no live runner
    _runner('mini')
    assert runner_queue.resolve_target('auto') == ('queue', None)
    assert runner_queue.resolve_target('any') == ('queue', None)
    assert runner_queue.resolve_target('mini') == ('queue', 'mini')
    with pytest.raises(runner_queue.QueueError, match='No runner is named "air". Known runners: mini.'):
        runner_queue.resolve_target('air')

    monkeypatch.setitem(runner_queue.ENV_VALUES, 'RESEARCH_RUNNERS', '')
    assert runner_queue.resolve_target('auto') == ('local', None)
    with pytest.raises(runner_queue.QueueError, match='not turned on'):
        runner_queue.resolve_target('any')


def test_two_runners_never_take_the_same_job(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    ids = [_backtest() for _ in range(6)]
    for session_id in ids:
        _enqueue(project, session_id)
    claimed = {'a': [], 'b': []}

    def take(name):
        while True:
            with pg.connection_context():
                job = runner_queue.claim_next(name, 8, 8)
            if job is None:
                return
            claimed[name].append(job['session_id'])

    threads = [threading.Thread(target=take, args=(name,)) for name in claimed]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    taken = claimed['a'] + claimed['b']
    assert sorted(taken) == sorted(ids) and len(set(taken)) == 6


def test_claims_respect_the_target_the_version_and_exclusions(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    for_mini = _backtest()
    _enqueue(project, for_mini, target='mini')
    assert _claim('air') is None

    job = _claim('mini')
    assert job['session_id'] == for_mini and job['attempt'] == 1 and job['packages'] == ['numpy', 'talib']

    other = _backtest()
    _enqueue(project, other)
    RunnerJob.update(jesse_version='0.0.1').where(RunnerJob.session_id == other).execute()
    assert _claim('mini') is None


def test_a_runner_missing_a_package_gives_the_job_to_another(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    _runner('mini')
    _runner('air')
    session_id = _backtest()
    _enqueue(project, session_id)

    job = _claim('mini')
    runner_queue.release(job, 'mini', 'Runner mini does not have the package(s) talib.')

    row = RunnerJob.get(RunnerJob.session_id == session_id)
    assert (row.status, row.attempt, row.excluded) == ('queued', 0, ',mini,')
    assert _claim('mini') is None
    job = _claim('air')
    assert job is not None
    runner_queue.release(job, 'air', 'Runner air does not have the package(s) talib.')

    row = RunnerJob.get(RunnerJob.session_id == session_id)
    assert row.status == 'failed' and 'No runner can run this job' in row.error
    assert _session(session_id).status == 'stopped'


def test_a_lost_runners_job_is_queued_again_until_its_attempts_run_out(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    session_id = _backtest()
    _enqueue(project, session_id)
    lapsed = _now() - 10 * 60 * 1000

    for attempt in (1, 2):
        job = _claim(f'runner{attempt}')
        session_liveness.claim('backtest', session_id, mark_running=True, claim_id=job['claim_id'])
        BacktestSession.update(heartbeat_at=lapsed).where(BacktestSession.id == session_id).execute()
        from jesse.models.BacktestSession import get_backtest_session_by_id
        assert get_backtest_session_by_id(session_id).status == 'queued'
        assert 'stopped answering' in RunnerJob.get(RunnerJob.session_id == session_id).error

    job = _claim('runner3')
    session_liveness.claim('backtest', session_id, mark_running=True, claim_id=job['claim_id'])
    BacktestSession.update(heartbeat_at=lapsed).where(BacktestSession.id == session_id).execute()
    from jesse.models.BacktestSession import get_backtest_session_by_id
    assert get_backtest_session_by_id(session_id).status == 'stopped'
    row = RunnerJob.get(RunnerJob.session_id == session_id)
    assert row.status == 'failed' and 'Lost its runner (runner3) 3 times' in row.error


def test_a_stale_worker_cannot_overwrite_the_run_that_replaced_it(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    session_id = _backtest()
    _enqueue(project, session_id)
    old = _claim('runner1')
    session_liveness.claim('backtest', session_id, mark_running=True, claim_id=old['claim_id'])
    # The job moved to another runner.
    BacktestSession.update(claim_id='newer-claim').where(BacktestSession.id == session_id).execute()

    session_liveness.set_claim(old['claim_id'])
    try:
        update_backtest_session_status(session_id, 'finished')
    finally:
        session_liveness.set_claim(None)
    assert _session(session_id).status == 'running'

    session_liveness.set_claim('newer-claim')
    try:
        update_backtest_session_status(session_id, 'finished')
    finally:
        session_liveness.set_claim(None)
    assert _session(session_id).status == 'finished'


def test_cancelling_drops_a_queued_job_and_signals_a_running_one(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    notified = []
    monkeypatch.setattr(runner_queue, 'notify', lambda channel, payload='': notified.append((channel, payload)))
    queued = _backtest()
    _enqueue(project, queued)
    runner_queue.cancel(queued)
    assert RunnerJob.get(RunnerJob.session_id == queued).status == 'cancelled'
    assert _session(queued).status == 'cancelled'

    running = _backtest()
    _enqueue(project, running)
    _claim('mini')
    runner_queue.cancel(running)
    assert RunnerJob.get(RunnerJob.session_id == running).status == 'cancelled'
    assert (runner_queue.CHANNEL_CANCEL, running) in notified


def test_queuing_again_replaces_a_waiting_job_but_not_a_running_one(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    session_id = _backtest()
    _enqueue(project, session_id)
    _enqueue(project, session_id)
    statuses = sorted(job.status for job in RunnerJob.select().where(RunnerJob.session_id == session_id))
    assert statuses == ['cancelled', 'queued']

    _claim('mini')
    with pytest.raises(runner_queue.QueueError, match='already running on a runner'):
        _enqueue(project, session_id)


def test_shutdown_gives_a_job_back_without_using_an_attempt(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    session_id = _backtest()
    _enqueue(project, session_id)
    job = _claim('mini')

    runner_queue.requeue(job, 'Runner mini shut down; queued again.')

    row = RunnerJob.get(RunnerJob.session_id == session_id)
    assert (row.status, row.attempt, row.claim_id) == ('queued', 0, None)
    assert _session(session_id).status == 'queued'


def test_the_runners_list_and_queue_info(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    _runner('mini')
    _runner('air', version='0.0.1', seconds_ago=600)
    session_id = _backtest()
    _enqueue(project, session_id)
    _claim('mini')

    payload = runner_queue.runners_payload()
    runners = {r['name']: r for r in payload['runners']}
    assert runners['mini']['alive'] and runners['mini']['compatible']
    assert runners['mini']['running'] == [{'session_id': session_id, 'session_type': 'backtest'}]
    assert not runners['air']['alive'] and not runners['air']['compatible'] and runners['air']['cores_free'] == 0
    info = runner_queue.queue_info(session_id)
    assert info['job_status'] == 'running' and info['attempt'] == 1 and info['target'] == 'any'


def test_unused_code_is_cleaned_up_but_waiting_jobs_keep_theirs(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    session_id = _backtest()
    _enqueue(project, session_id)
    long_ago = _now() - 10 * 24 * 3600 * 1000
    CodeBlob.update(last_used_at=long_ago).execute()
    orphan = 'f' * 64
    CodeBlob.insert(hash=orphan, content=b'x', size=1, created_at=long_ago, last_used_at=long_ago).execute()

    runner_queue.sweep()

    assert CodeBlob.get_or_none(CodeBlob.hash == orphan) is None
    manifest = json.loads(RunnerJob.get(RunnerJob.session_id == session_id).code_manifest)
    assert CodeBlob.select().where(CodeBlob.hash.in_(list(manifest.values()))).count() == len(set(manifest.values()))


def test_a_runner_caps_cpu_cores_at_its_own_count(monkeypatch):
    import multiprocessing
    monkeypatch.setattr(multiprocessing, 'cpu_count', lambda: 8)
    optimization = ['sid', {'cpu_cores': 16, 'trials': 5}] + [None] * 9 + [16, {}]
    runner_worker._fit_cpu_cores('optimization', optimization)
    assert optimization[11] == 8 and optimization[1]['cpu_cores'] == 8

    small = ['sid', {'cpu_cores': 2}] + [None] * 9 + [2, {}]
    runner_worker._fit_cpu_cores('monte_carlo', small)
    assert small[11] == 2 and small[1]['cpu_cores'] == 2


def test_only_runners_with_cores_on_this_version_count_for_auto(pg):
    Runner.insert(name='hub', host='hub', cores_budget=0, cores_used=0, cpu_cores=8, jesse_version=runner_queue.jesse_version(),
                  started_at=_now(), last_seen=_now()).execute()
    _runner('old', version='0.0.1')
    assert runner_queue.resolve_target('auto') == ('local', None)
    _runner('mini')
    assert runner_queue.resolve_target('auto') == ('queue', None)


def _optimization_request(session_id, where=None):
    from jesse.services.web import OptimizationRequestJson
    return OptimizationRequestJson(
        id=session_id, exchange='Binance Spot', routes=[{'exchange': 'Binance Spot', 'strategy': 'S', 'symbol': 'BTC-USDT',
                                                         'timeframe': '4h'}], data_routes=[], config={},
        training_start_date='2024-01-01', training_finish_date='2024-02-01',
        testing_start_date='2024-02-01', testing_finish_date='2024-03-01',
        optimal_total=10, fast_mode=True, cpu_cores=1, state={}, where=where,
    )


@pytest.mark.parametrize('route', ['resume_optimization', 'rerun_optimization'])
def test_a_queued_optimization_is_not_started_twice(monkeypatch, route):
    import asyncio
    from jesse.controllers import optimization_controller as controller
    calls = []
    monkeypatch.setattr(controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(controller, 'get_optimization_session_by_id_from_db',
                        lambda session_id: SimpleNamespace(id=session_id, status='queued'))
    monkeypatch.setattr(controller.process_manager, 'add_task', lambda *args: calls.append(args))
    monkeypatch.setattr(controller.runner_queue, 'enqueue', lambda *args: calls.append(args))

    response = asyncio.run(getattr(controller, route)(_optimization_request('opt-id', where='any')))

    assert response.status_code == 409 and b'already queued' in response.body
    assert calls == []


def test_a_rerun_that_cannot_be_queued_stops_with_the_reason(monkeypatch):
    import asyncio
    from jesse.controllers import optimization_controller as controller
    statuses, exceptions = [], []
    monkeypatch.setattr(controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(controller, 'get_optimization_session_by_id_from_db',
                        lambda session_id: SimpleNamespace(id=session_id, status='finished'))
    monkeypatch.setattr(controller, 'reset_optimization_session', lambda session_id: statuses.append('reset'))
    monkeypatch.setattr(controller, 'update_optimization_session_status', lambda sid, status: statuses.append(status))
    monkeypatch.setattr(controller, 'add_session_exception', lambda sid, error, tb: exceptions.append(error))
    monkeypatch.setattr(controller.runner_queue, 'resolve_target', lambda where: ('queue', None))

    def refuse(*args):
        raise runner_queue.QueueError('Strategy "S" was not found in /project/strategies.')

    monkeypatch.setattr(controller.runner_queue, 'enqueue', refuse)

    response = asyncio.run(controller.rerun_optimization(_optimization_request('opt-id', where='any')))

    assert response.status_code == 400
    assert statuses == ['reset', 'stopped'] and exceptions == ['Strategy "S" was not found in /project/strategies.']


# ---------------------------------------------------------------------------
# RUNNER_ORDER placement and machine stats
# ---------------------------------------------------------------------------

def _set_free(name, budget, used):
    Runner.update(cores_budget=budget, cores_used=used).where(Runner.name == name).execute()


@pytest.mark.parametrize(('order', 'mini_free', 'expect_hub', 'expect_mini'), [
    (None, 3, True, True),                 # no order: first come first served
    ('macmini,hub', 3, False, True),       # the mini first while it has room
    ('macmini,hub', 0, True, False),       # the hub only when the mini is full
    ('macmini', 0, False, False),          # only the mini (full now), the hub just orchestrates
    ('hub,*', 1, True, False),             # the hub first, then any other runner (hub has room)
])
def test_runner_order_decides_who_takes_a_job(pg, project, monkeypatch, order, mini_free, expect_hub, expect_mini):
    monkeypatch.chdir(project)
    if order:
        monkeypatch.setitem(runner_queue.ENV_VALUES, 'RUNNER_ORDER', order)
    _runner('hub')
    _runner('macmini')
    _set_free('hub', 1, 0)
    _set_free('macmini', 3, 3 - mini_free)
    session_id = _backtest()
    _enqueue(project, session_id)

    hub_job = _claim('hub')
    if hub_job:
        runner_queue.requeue(hub_job, 'test')
    mini_job = _claim('macmini')

    assert (hub_job is not None) is expect_hub
    assert (mini_job is not None) is expect_mini


def test_a_lower_ranked_runner_leaves_the_preferred_one_just_its_free_cores(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.setitem(runner_queue.ENV_VALUES, 'RUNNER_ORDER', 'macmini,hub')
    _runner('hub')
    _runner('macmini')
    _set_free('macmini', 3, 1)  # 2 free
    ids = []
    for _ in range(5):
        ids.append(_backtest())
        _enqueue(project, ids[-1])

    taken = []
    while True:
        job = runner_queue.claim_next('hub', 8, 8)
        if job is None:
            break
        taken.append(job['session_id'])

    assert taken == ids[2:]  # the two oldest stay for the mini


def test_auto_queues_when_an_order_is_set_even_with_no_runner_connected(pg, monkeypatch):
    monkeypatch.setitem(runner_queue.ENV_VALUES, 'RUNNER_ORDER', 'macmini')
    assert runner_queue.resolve_target('auto') == ('queue', None)


def test_runners_report_how_busy_their_machine_is(pg):
    _runner('macmini')
    Runner.update(cpu_percent=37.5, load_1m=3.1, memory_total_bytes=16 * 1024 ** 3,
                  memory_used_bytes=4 * 1024 ** 3).where(Runner.name == 'macmini').execute()

    runner = runner_queue.runners_payload()['runners'][0]

    assert (runner['cpu_percent'], runner['load_1m'], runner['memory_total_gb'], runner['memory_used_gb'],
            runner['memory_percent']) == (37.5, 3.1, 16.0, 4.0, 25.0)


def test_machine_stats_work_without_psutil(monkeypatch):
    import builtins
    from jesse.services import machine_stats
    real_import = builtins.__import__

    def no_psutil(name, *args, **kwargs):
        if name == 'psutil':
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_psutil)
    stats = machine_stats.collect()
    assert stats['memory_total_bytes'] and stats['memory_used_bytes'] is not None
    assert 0 <= stats['memory_percent'] <= 100 and stats['cpu_percent'] is not None


def test_a_job_folder_sees_the_runner_projects_env(tmp_path):
    from jesse.services.runner import Runner as RunnerLoop
    project_dir, job_dir = tmp_path / 'project', tmp_path / 'project/storage/runner/jobs/x'
    job_dir.mkdir(parents=True)
    (project_dir / '.env').write_text('POSTGRES_HOST=db\n')

    RunnerLoop('mini', 1, hub=False, project_root=str(project_dir))._link_env(str(job_dir))

    assert (job_dir / '.env').read_text() == 'POSTGRES_HOST=db\n'
    import shutil
    shutil.rmtree(job_dir)
    assert (project_dir / '.env').exists()  # removing the job folder leaves the project's .env alone


def test_a_version_mismatch_stops_a_standalone_runner_and_pauses_one_inside_jesse_run(pg, monkeypatch):
    from jesse.services.runner import Runner as RunnerLoop
    Runner.insert(name='macbook', host='macbook', role='hub', cores_budget=1, cores_used=0, cpu_cores=16, jesse_version='9.9.9',
                  started_at=_now(), last_seen=_now()).execute()
    printed = []
    monkeypatch.setattr('jesse.services.runner._log', lambda text, level='info': printed.append((level, text)))

    standalone = RunnerLoop('mini', 2, hub=False, standalone=True)
    standalone._check_version()
    assert standalone.fatal_error and 'the hub "macbook" runs Jesse 9.9.9' in standalone.fatal_error
    assert standalone._stopping.is_set()

    inside = RunnerLoop('mini', 2, hub=False, standalone=False)
    inside._check_version()
    assert inside.fatal_error is None and inside._blocked and not inside._stopping.is_set()
    assert ('error', 'This runner takes no jobs until the versions match.') in printed

    Runner.update(jesse_version=runner_queue.jesse_version()).where(Runner.name == 'macbook').execute()
    inside._check_version()
    assert inside._blocked is None
    assert ('good', 'The hub now runs the same Jesse version; taking jobs again.') in printed


def test_a_runner_that_stops_shows_as_recently_offline_and_survives_cleanup(pg, project, monkeypatch):
    from jesse.services.runner import Runner as RunnerLoop
    monkeypatch.chdir(project)
    loop = RunnerLoop('mini', 2, hub=False, standalone=True)
    loop._heartbeat()
    assert runner_queue.runners_payload()['runners'][0]['alive'] is True

    loop._heartbeat(offline=True)
    runner_queue.sweep()

    runner = runner_queue.runners_payload()['runners'][0]
    assert runner['name'] == 'mini' and runner['alive'] is False and runner['last_seen_seconds_ago'] < 120



def _enqueue_job(project, function='backtest', cores=None, target=None):
    session_id = _backtest()
    os.chdir(project)
    arguments = [session_id, False, {}] if function == 'backtest' else [session_id, {'cpu_cores': cores}] + [None] * 9 + [cores, {}]
    runner_queue.enqueue('backtest', function, arguments, ['Variant7'], target)
    return session_id


def test_a_job_uses_the_cores_it_asked_for(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    backtest = _enqueue_job(project)
    optimization = _enqueue_job(project, 'optimization', cores=6)

    assert {str(j.session_id): j.cores for j in RunnerJob.select()} == {backtest: 1, optimization: 6}
    assert runner_queue.claim_next('mini', 8, 8)['cost'] == 1
    assert runner_queue.claim_next('mini', 7, 8)['cost'] == 6
    assert runner_queue.claim_next('mini', 1, 8) is None


def test_a_big_job_is_never_overtaken_on_the_runner_that_waits_for_it(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    _runner('mini')
    _set_free('mini', 8, 3)  # three backtests running
    optimization = _enqueue_job(project, 'optimization', cores=8)
    _enqueue_job(project)  # a backtest that would fit

    assert runner_queue.claim_next('mini', 5, 8) is None  # drains instead of starting the backtest
    _set_free('mini', 8, 0)
    assert runner_queue.claim_next('mini', 8, 8)['session_id'] == optimization


def test_other_runners_keep_working_while_one_waits_for_a_big_job(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    _runner('mini')
    _runner('air')
    _set_free('mini', 8, 3)
    _set_free('air', 4, 0)
    optimization = _enqueue_job(project, 'optimization', cores=8)
    backtest = _enqueue_job(project)

    # The air could only give it 4 of its 8 cores, so it leaves it to the mini and takes the backtest.
    assert runner_queue.claim_next('air', 4, 4)['session_id'] == backtest
    assert runner_queue.claim_next('mini', 5, 8) is None
    assert RunnerJob.get(RunnerJob.session_id == optimization).status == 'queued'


def test_a_job_bigger_than_every_runner_is_capped_to_the_biggest(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    _runner('mini')
    _set_free('mini', 7, 0)
    _enqueue_job(project, 'optimization', cores=16)

    job = runner_queue.claim_next('mini', 7, 7)
    assert job['cores'] == 16 and job['cost'] == 7


def test_the_order_decides_which_runner_waits_for_a_big_job(pg, project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.setitem(runner_queue.ENV_VALUES, 'RUNNER_ORDER', 'air,mini')
    _runner('mini')
    _runner('air')
    _set_free('mini', 8, 2)
    _set_free('air', 8, 2)
    _enqueue_job(project, 'optimization', cores=8)
    backtest = _enqueue_job(project)

    assert runner_queue.claim_next('air', 6, 8) is None  # air is first in the order: it waits
    assert runner_queue.claim_next('mini', 6, 8)['session_id'] == backtest


# ---------------------------------------------------------------------------
# A runner's own bookkeeping: lost jobs and finished jobs
# ---------------------------------------------------------------------------

def _runner_with_claimed_job(project, tmp_path, monkeypatch):
    from jesse.services import runner as runner_module
    from jesse.services.multiprocessing import process_manager

    session_id = _backtest()
    _enqueue(project, session_id)
    job = _claim('mini')
    job_dir = tmp_path / 'jobs' / session_id
    (job_dir / 'storage' / 'logs').mkdir(parents=True)
    (job_dir / 'storage' / 'logs' / 'run.txt').write_text('log')
    job['job_dir'] = str(job_dir)
    cancelled = []
    monkeypatch.setattr(process_manager, 'cancel_process', lambda client_id, notify_runners=True: cancelled.append(client_id))
    runner = runner_module.Runner('mini', 8, hub=False, project_root=str(tmp_path))
    runner.jobs[session_id] = job
    return runner, job, cancelled


def test_a_runner_never_takes_a_session_it_still_has_a_worker_for(pg, project, monkeypatch):
    first, second = _backtest(), _backtest()
    _enqueue(project, first)
    _enqueue(project, second)

    assert runner_queue.claim_next('mini', 8, 8, busy_sessions={first})['session_id'] == second


def test_a_lost_job_keeps_its_folder_and_cores_until_its_worker_exits(pg, project, tmp_path, monkeypatch):
    runner, job, cancelled = _runner_with_claimed_job(project, tmp_path, monkeypatch)
    session_id = job['session_id']
    # The hub gave the job back to the queue (its lease ran out) while the worker kept running here.
    RunnerJob.update(status='queued', claim_id=None, claimed_by=None).where(RunnerJob.id == job['id']).execute()

    runner._drop_lost_jobs()

    assert cancelled == [session_id]
    assert runner.cores_used() == 1 and os.path.isdir(job['job_dir'])
    assert runner_queue.claim_next('mini', 7, 8, busy_sessions=runner._busy_sessions()) is None

    runner.on_worker_exit(session_id, 1)

    assert not os.path.exists(job['job_dir'])
    assert runner.cores_used() == 0 and runner._finished.empty()
    assert runner_queue.claim_next('mini', 8, 8, busy_sessions=runner._busy_sessions())['session_id'] == session_id


def test_a_finished_job_is_completed_off_the_process_managers_thread(pg, project, tmp_path, monkeypatch):
    runner, job, _ = _runner_with_claimed_job(project, tmp_path, monkeypatch)
    session_id = job['session_id']
    update_backtest_session_status(session_id, 'finished')

    runner.on_worker_exit(session_id, 0)

    # Its cores are free at once, but the session stays busy here until its files are sent.
    assert runner.cores_used() == 0 and session_id in runner._busy_sessions()
    assert RunnerJob.get(RunnerJob.id == job['id']).status == 'running'

    threading.Thread(target=runner._complete_finished_jobs, daemon=True).start()
    runner._finished.join()

    assert RunnerJob.get(RunnerJob.id == job['id']).status == 'done'
    assert [f.path for f in RunnerFile.select().where(RunnerFile.session_id == session_id)] == ['storage/logs/run.txt']
    assert not os.path.exists(job['job_dir']) and session_id not in runner._busy_sessions()
