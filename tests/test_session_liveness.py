"""Session owners and worker liveness for research sessions shared by several Jesse instances."""
import asyncio
import time
import uuid
from types import SimpleNamespace

import peewee
import pytest

from jesse.controllers import monte_carlo_controller, optimization_controller
from jesse.models.BacktestSession import BacktestSession, get_backtest_session_by_id, get_backtest_sessions
from jesse.models.MonteCarloSession import MonteCarloCandlesSession, MonteCarloSession, MonteCarloTradesSession
from jesse.models.OptimizationSession import (
    OptimizationSession,
    get_optimization_session_by_id,
    get_running_optimization_session_id,
)
from jesse.models.SignificanceTestSession import SignificanceTestSession
from jesse.services import redis as coordinator
from jesse.services import session_liveness
from jesse.services.multiprocessing import ProcessManager
from jesse.services.web import MonteCarloRequestJson, OptimizationRequestJson

HERE = 'this-host:9000'
OTHER = 'other-host:9005'
MODELS = [BacktestSession, OptimizationSession, MonteCarloSession, MonteCarloTradesSession,
          MonteCarloCandlesSession, SignificanceTestSession]


@pytest.fixture
def db(monkeypatch):
    database = peewee.SqliteDatabase(':memory:')
    with database.bind_ctx(MODELS):
        database.create_tables(MODELS)
        # The liveness writes are skipped in unit-test mode; these tests run them on SQLite.
        monkeypatch.setattr(session_liveness, 'jh', SimpleNamespace(is_unit_testing=lambda: False))
        monkeypatch.setattr(session_liveness, '_owner', HERE)
        monkeypatch.setattr(session_liveness, 'instance_owner', lambda: HERE)
        yield database


@pytest.fixture
def active(monkeypatch):
    """The session ids this instance's coordinator has workers for."""
    ids = set()
    monkeypatch.setattr(coordinator, 'is_process_active', lambda client_id: str(client_id) in ids)
    return ids


def _ms(seconds_ago: float = 0) -> int:
    return int((time.time() - seconds_ago) * 1000)


def _row(model, status='running', owner=HERE, heartbeat_seconds_ago=600, **fields):
    session_id = str(uuid.uuid4())
    values = {'id': session_id, 'status': status, 'owner': owner, 'created_at': _ms(), 'updated_at': _ms(), **fields}
    if heartbeat_seconds_ago is not None:
        values['heartbeat_at'] = _ms(heartbeat_seconds_ago)
    model.insert(**values).execute()
    return session_id


def _status(model, session_id):
    return model.get(model.id == session_id).status


# ---------------------------------------------------------------------------
# Claiming and judging a session
# ---------------------------------------------------------------------------

def test_claim_records_this_instance_and_can_mark_the_session_running(db):
    session_id = _row(OptimizationSession, status='draft', owner=None, heartbeat_seconds_ago=None)

    session_liveness.claim('optimization', session_id, mark_running=True)

    row = OptimizationSession.get(OptimizationSession.id == session_id)
    assert (row.status, row.owner) == ('running', HERE)
    assert abs(row.heartbeat_at - _ms()) < 5_000


@pytest.mark.parametrize(('owner', 'heartbeat_seconds_ago', 'worker', 'allow_unowned', 'gone'), [
    (HERE, 600, False, True, True),        # owned, quiet, no worker: gone
    (HERE, 600, True, True, False),        # owned, worker alive
    (HERE, 5, False, True, False),         # just claimed: grace period
    (OTHER, 600, False, True, False),      # another instance's session: never judged here
    (None, None, False, True, True),       # legacy row: judged as Jesse always did
    (None, None, False, False, False),     # legacy row where the caller opts out
])
def test_worker_is_gone_only_for_this_instances_quiet_sessions(db, active, owner, heartbeat_seconds_ago,
                                                               worker, allow_unowned, gone):
    session_id = _row(OptimizationSession, owner=owner, heartbeat_seconds_ago=heartbeat_seconds_ago)
    if worker:
        active.add(session_id)
    session = OptimizationSession.get(OptimizationSession.id == session_id)

    assert session_liveness.worker_is_gone(session, allow_unowned=allow_unowned) is gone


# ---------------------------------------------------------------------------
# Reading sessions
# ---------------------------------------------------------------------------

def test_reading_another_instances_running_optimization_leaves_it_running(db, active):
    theirs = _row(OptimizationSession, owner=OTHER)
    mine = _row(OptimizationSession, owner=HERE)

    assert get_optimization_session_by_id(theirs).status == 'running'
    assert get_optimization_session_by_id(mine).status == 'stopped'
    assert (_status(OptimizationSession, theirs), _status(OptimizationSession, mine)) == ('running', 'stopped')


def test_the_running_session_shown_here_is_one_this_instance_owns(db, active):
    theirs = _row(OptimizationSession, owner=OTHER, updated_at=_ms() + 10_000)
    mine = _row(OptimizationSession, owner=HERE)
    active.add(mine)

    assert get_running_optimization_session_id() == mine
    assert _status(OptimizationSession, theirs) == 'running'


def test_an_orphaned_backtest_is_stopped_with_a_reason_but_unowned_ones_are_left_alone(db, active):
    orphan = _row(BacktestSession, owner=HERE)
    legacy = _row(BacktestSession, owner=None, heartbeat_seconds_ago=None)
    alive = _row(BacktestSession, owner=HERE)
    active.add(alive)

    stopped = get_backtest_session_by_id(orphan)
    listed = {str(s.id): s.status for s in get_backtest_sessions()}

    assert stopped.status == 'stopped'
    assert 'worker is no longer running' in stopped.exception
    assert listed == {orphan: 'stopped', legacy: 'running', alive: 'running'}


# ---------------------------------------------------------------------------
# Worker exit
# ---------------------------------------------------------------------------

def test_a_worker_that_exits_without_reporting_leaves_a_stopped_session(db, active):
    session_id = _row(OptimizationSession, owner=HERE, heartbeat_seconds_ago=1)

    assert session_liveness.reconcile_exited_worker(session_id, -9) == ['optimization']

    row = OptimizationSession.get(OptimizationSession.id == session_id)
    assert row.status == 'stopped'
    assert 'exited (exit code -9) without reporting a result' in row.exception


@pytest.mark.parametrize('case', ['finished', 'other_owner', 'rerun'])
def test_worker_exit_does_not_touch_finished_foreign_or_rerun_sessions(db, active, case):
    session_id = _row(
        BacktestSession,
        status='finished' if case == 'finished' else 'running',
        owner=OTHER if case == 'other_owner' else HERE,
    )
    if case == 'rerun':
        active.add(session_id)  # a newer worker already runs the same session

    assert session_liveness.reconcile_exited_worker(session_id, 0) == []
    assert _status(BacktestSession, session_id) == ('finished' if case == 'finished' else 'running')


def test_worker_exit_also_stops_the_running_parts_of_a_monte_carlo_session(db, active):
    session_id = _row(MonteCarloSession, owner=HERE)
    MonteCarloTradesSession.insert(id=str(uuid.uuid4()), monte_carlo_session_id=session_id, num_scenarios=10,
                                   status='running', created_at=_ms(), updated_at=_ms()).execute()
    MonteCarloCandlesSession.insert(id=str(uuid.uuid4()), monte_carlo_session_id=session_id, num_scenarios=10,
                                    status='finished', pipeline_type='x', created_at=_ms(), updated_at=_ms()).execute()

    assert session_liveness.reconcile_exited_worker(session_id, 1) == ['monte_carlo']
    assert _status(MonteCarloSession, session_id) == 'stopped'
    assert MonteCarloTradesSession.get().status == 'stopped'
    assert 'exited (exit code 1)' in MonteCarloTradesSession.get().exception
    assert MonteCarloCandlesSession.get().status == 'finished'


def test_the_process_manager_reconciles_without_ever_raising(monkeypatch):
    calls = []
    monkeypatch.setattr(session_liveness, 'reconcile_exited_worker', lambda *args: calls.append(args) or ['backtest'])
    ProcessManager._reconcile_exited_session('abc', -9)

    def broken(*args):
        raise RuntimeError('database is down')

    monkeypatch.setattr(session_liveness, 'reconcile_exited_worker', broken)
    ProcessManager._reconcile_exited_session('abc', -9)  # logged, not raised

    assert calls == [('abc', -9)]


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def test_heartbeat_refreshes_the_tracked_running_session_at_most_every_interval(db):
    session_id = _row(OptimizationSession, owner=HERE, heartbeat_seconds_ago=600)
    session_liveness.track('optimize', session_id)

    session_liveness.beat(42)
    first = OptimizationSession.get(OptimizationSession.id == session_id)
    assert abs(first.heartbeat_at - _ms()) < 5_000 and first.progress == 42

    session_liveness.beat(43)  # within the interval: no write
    assert OptimizationSession.get(OptimizationSession.id == session_id).progress == 42


def test_heartbeat_never_revives_an_ended_session_or_tracks_other_modes(db):
    stopped = _row(BacktestSession, status='stopped', owner=HERE, heartbeat_seconds_ago=600)
    session_liveness.track('backtest', stopped)
    session_liveness.beat(10)
    row = BacktestSession.get(BacktestSession.id == stopped)
    assert (row.status, row.progress) == ('stopped', None)

    session_liveness.track('livetrade', str(uuid.uuid4()))
    assert session_liveness._tracked is None
    session_liveness.beat(10)  # nothing tracked: no-op


# ---------------------------------------------------------------------------
# Start routes
# ---------------------------------------------------------------------------

def _optimization_request(session_id: str) -> OptimizationRequestJson:
    return OptimizationRequestJson(
        id=session_id, exchange='Binance Spot', routes=[], data_routes=[], config={},
        training_start_date='2024-01-01', training_finish_date='2024-02-01',
        testing_start_date='2024-02-01', testing_finish_date='2024-03-01',
        optimal_total=10, fast_mode=True, cpu_cores=1, state={},
    )


@pytest.fixture
def resume_route(monkeypatch):
    calls = []
    session = SimpleNamespace(id='opt-id', status='draft')
    monkeypatch.setattr(optimization_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(optimization_controller, 'get_optimization_session_by_id_from_db', lambda session_id: session)
    monkeypatch.setattr(optimization_controller, 'get_optimization_session_for_load_more', lambda s: {'status': s.status})
    monkeypatch.setattr(session_liveness, 'has_live_worker', lambda s: s.status == 'running')
    monkeypatch.setattr(session_liveness, 'claim', lambda *args, **kwargs: calls.append(('claim', args, kwargs)))
    monkeypatch.setattr(session_liveness, 'release_failed_start', lambda *args: calls.append(('release', args)))
    monkeypatch.setattr(optimization_controller.process_manager, 'add_task', lambda *args: calls.append(('worker', args[1])))
    return SimpleNamespace(calls=calls, session=session)


def test_resume_marks_the_optimization_running_before_starting_its_worker(resume_route):
    response = asyncio.run(optimization_controller.resume_optimization(_optimization_request('opt-id')))

    assert response.status_code == 200
    assert resume_route.calls == [
        ('claim', ('optimization', 'opt-id'), {'mark_running': True}),
        ('worker', 'opt-id'),
    ]
    assert b'"status":"running"' in response.body


def test_resume_refuses_to_start_a_second_worker(resume_route):
    resume_route.session.status = 'running'

    response = asyncio.run(optimization_controller.resume_optimization(_optimization_request('opt-id')))

    assert response.status_code == 409
    assert resume_route.calls == []


def test_a_worker_that_cannot_start_leaves_a_stopped_session(resume_route, monkeypatch):
    def refuse(*args):
        raise RuntimeError('Jesse is shutting down; cannot launch another session')

    monkeypatch.setattr(optimization_controller.process_manager, 'add_task', refuse)

    response = asyncio.run(optimization_controller.resume_optimization(_optimization_request('opt-id')))

    assert response.status_code == 500
    assert resume_route.calls[-1] == ('release', ('optimization', 'opt-id', 'RuntimeError: Jesse is shutting down; cannot launch another session'))


def test_monte_carlo_resume_claims_the_session_before_starting(monkeypatch):
    calls = []
    session = SimpleNamespace(id='mc-id', status='draft', state=None, state_json={})
    monkeypatch.setattr(monte_carlo_controller.jh, 'validate_cwd', lambda: None)
    monkeypatch.setattr(monte_carlo_controller, 'get_monte_carlo_session_by_id', lambda session_id: session)
    monkeypatch.setattr(monte_carlo_controller, 'get_monte_carlo_session_for_load_more', lambda s: {})
    monkeypatch.setattr(session_liveness, 'has_live_worker', lambda s: False)
    monkeypatch.setattr(session_liveness, 'claim', lambda *args, **kwargs: calls.append(('claim', args, kwargs)))
    monkeypatch.setattr(monte_carlo_controller.process_manager, 'add_task', lambda *args: calls.append(('worker', args[1])))
    request = MonteCarloRequestJson(
        id='mc-id', exchange='Binance Spot', routes=[], data_routes=[], config={'cpu_cores': 1},
        start_date='2024-01-01', finish_date='2024-02-01', run_trades=True, run_candles=False,
        num_scenarios=10, fast_mode=True, cpu_cores=1, state={},
    )

    response = asyncio.run(monte_carlo_controller.resume_monte_carlo(request))

    assert response.status_code == 200
    assert calls == [('claim', ('monte_carlo', 'mc-id'), {'mark_running': True}), ('worker', 'mc-id')]
