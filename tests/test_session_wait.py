"""wait_for_sessions (MCP) and the batch session status it reads (/session-results/status)."""
import json
import time
import uuid
from types import SimpleNamespace

import peewee
import pytest

from jesse.controllers import session_results_controller
from jesse.mcp.tools.services import session_wait
from jesse.models.BacktestSession import BacktestSession
from jesse.models.MonteCarloSession import MonteCarloCandlesSession, MonteCarloSession, MonteCarloTradesSession
from jesse.models.OptimizationSession import OptimizationSession
from jesse.models.SignificanceTestSession import SignificanceTestSession
from jesse.services import redis as coordinator
from jesse.services import session_liveness, session_status
from jesse.services.web import SessionStatusRequestJson

HERE = 'this-host:9000'
MODELS = [BacktestSession, OptimizationSession, MonteCarloSession, MonteCarloTradesSession,
          MonteCarloCandlesSession, SignificanceTestSession]


def _ms(seconds_ago: float = 0) -> int:
    return int((time.time() - seconds_ago) * 1000)


@pytest.fixture
def db(monkeypatch):
    database = peewee.SqliteDatabase(':memory:')
    with database.bind_ctx(MODELS):
        database.create_tables(MODELS)
        monkeypatch.setattr(session_liveness, 'jh', SimpleNamespace(is_unit_testing=lambda: False))
        monkeypatch.setattr(session_liveness, 'machine_label', lambda: HERE)
        monkeypatch.setattr(session_liveness, 'now_ms', lambda: int(time.time() * 1000))
        monkeypatch.setattr(coordinator, 'is_process_active', lambda client_id: False)
        yield database


def _row(model, status='running', claimed_by=HERE, heartbeat_seconds_ago=5, **fields):
    session_id = str(uuid.uuid4())
    values = {'id': session_id, 'status': status, 'claimed_by': claimed_by, 'created_at': _ms(), 'updated_at': _ms(), **fields}
    if heartbeat_seconds_ago is not None:
        values['heartbeat_at'] = _ms(heartbeat_seconds_ago)
    model.insert(**values).execute()
    return session_id


# ---------------------------------------------------------------------------
# /session-results/status
# ---------------------------------------------------------------------------

def test_status_reports_each_session_in_the_order_asked(db):
    backtest = _row(BacktestSession, progress=37.5)
    optimization = _row(OptimizationSession, claimed_by='other-host:9005', heartbeat_seconds_ago=20,
                        progress_at=_ms(120), completed_trials=4, total_trials=10)
    monte_carlo = _row(MonteCarloSession)
    MonteCarloCandlesSession.insert(id=str(uuid.uuid4()), monte_carlo_session_id=monte_carlo, num_scenarios=200,
                                    completed_scenarios=50, status='running', pipeline_type='x',
                                    created_at=_ms(), updated_at=_ms()).execute()
    unknown = str(uuid.uuid4())

    result = session_status.get_statuses([optimization, 'not-an-id', backtest, unknown, monte_carlo])
    sessions = result['sessions']

    assert [s['session_id'] for s in sessions] == [optimization, 'not-an-id', backtest, unknown, monte_carlo]
    assert sessions[0]['session_type'] == 'optimization'
    assert sessions[0]['progress'] == {'completed_trials': 4, 'total_trials': 10}
    assert sessions[0]['claimed_here'] is False and sessions[0]['claimed_by'] == 'other-host:9005'
    assert 119 < sessions[0]['progress_age_seconds'] < 130 and 19 < sessions[0]['heartbeat_age_seconds'] < 30
    assert sessions[1]['status'] == 'not_found' and sessions[3]['status'] == 'not_found'
    assert sessions[2]['progress'] == {'percent': 37.5} and sessions[2]['claimed_here'] is True
    assert sessions[4]['progress']['candles'] == {'completed_scenarios': 50, 'num_scenarios': 200, 'status': 'running'}
    assert result['machine'] == HERE and result['lease_seconds'] == 90


def test_status_reads_stop_a_session_whose_lease_ran_out(db):
    orphan = _row(OptimizationSession, heartbeat_seconds_ago=600)

    session = session_status.get_statuses([orphan])['sessions'][0]

    assert session['status'] == 'stopped'


def test_status_shows_the_first_line_of_a_session_error(db):
    failed = _row(BacktestSession, status='stopped', exception='InvalidStrategy: no sell\nTraceback ...')

    assert session_status.get_statuses([failed])['sessions'][0]['error'] == 'InvalidStrategy: no sell'


def test_status_drops_stale_progress_and_has_no_owner_verdict_for_unclaimed_sessions(db):
    finished = _row(BacktestSession, status='finished', progress=0.0)
    draft = _row(BacktestSession, status='draft', claimed_by=None, heartbeat_seconds_ago=None)

    first, second = session_status.get_statuses([finished, draft])['sessions']

    assert first['progress'] == {} and first['claimed_here'] is True
    assert second['claimed_here'] is None


@pytest.mark.parametrize(('session_ids', 'message'), [
    (None, 'non-empty list'),
    ([], 'non-empty list'),
    ('abc', 'non-empty list'),
    ([str(uuid.uuid4()) for _ in range(51)], 'At most 50'),
])
def test_status_endpoint_refuses_a_bad_request(session_ids, message):
    response = session_results_controller.get_session_statuses(SessionStatusRequestJson(session_ids=session_ids))

    body = json.loads(response.body)
    assert response.status_code == 400
    assert body['error_type'] == 'invalid_request' and message in body['message']


# ---------------------------------------------------------------------------
# wait_for_sessions
# ---------------------------------------------------------------------------

def _session(sid, status='running', kind='backtest', progress_age=5.0, **extra):
    return {'session_id': sid, 'session_type': kind, 'status': status, 'progress_age_seconds': progress_age,
            'heartbeat_age_seconds': 5.0, 'claimed_by': HERE, 'claimed_here': True, 'progress': {}, **extra}


@pytest.fixture
def jesse(monkeypatch):
    """Scripted status reads, a fake clock, and no real sleeping."""
    state = SimpleNamespace(reads=[], calls=0, now=0.0)

    def call(action, route, payload, timeout):
        assert route == '/session-results/status'
        state.calls += 1
        reply = state.reads[min(state.calls, len(state.reads)) - 1]
        return reply(payload['session_ids']) if callable(reply) else reply

    def sleep(seconds):
        state.now += seconds

    monkeypatch.setattr(session_wait, '_call', call)
    monkeypatch.setattr(session_wait.time, 'sleep', sleep)
    monkeypatch.setattr(session_wait.time, 'monotonic', lambda: state.now)
    return state


def _ok(*sessions):
    return {'status': 'success', 'sessions': list(sessions)}


def test_waits_until_every_session_ends(jesse):
    jesse.reads = [
        _ok(_session('a'), _session('b')),
        _ok(_session('a', 'finished'), _session('b')),
        _ok(_session('a', 'finished'), _session('b', 'stopped', error='InvalidStrategy: no sell')),
    ]

    result = session_wait.wait_for_sessions_service(['a', 'b'])

    assert result['done'] is True and jesse.calls == 3
    assert result['outcomes'] == {'finished': 1, 'ended': 1}
    assert result['sessions'][1]['error'] == 'InvalidStrategy: no sell'
    assert 'next' not in result


def test_until_any_returns_at_the_first_settled_session(jesse):
    jesse.reads = [_ok(_session('a'), _session('b')), _ok(_session('a'), _session('b', 'finished'))]

    result = session_wait.wait_for_sessions_service('["a", "b"]', until='any')

    assert result['done'] is True and jesse.calls == 2
    assert [s['outcome'] for s in result['sessions']] == ['running', 'finished']


def test_a_silent_running_session_counts_as_stalled(jesse):
    jesse.reads = [_ok(_session('opt', kind='optimization', progress_age=31 * 60, claimed_by='mini:9005', claimed_here=False))]

    result = session_wait.wait_for_sessions_service(['opt'])

    stalled = result['sessions'][0]
    assert result['done'] is True and stalled['outcome'] == 'stalled'
    assert 'Alive but no progress for 31 minutes (stall limit 30)' in stalled['note']
    assert "It runs on mini:9005: cancel it through that machine's Jesse." in stalled['note']


def test_stall_minutes_overrides_the_default(jesse):
    jesse.reads = [_ok(_session('bt', progress_age=3 * 60))]

    assert session_wait.wait_for_sessions_service(['bt'], stall_minutes=2)['sessions'][0]['outcome'] == 'stalled'
    assert session_wait.wait_for_sessions_service(['bt'], timeout_seconds=0)['sessions'][0]['outcome'] == 'running'


def test_a_session_without_heartbeats_is_never_called_stalled(jesse):
    jesse.reads = [_ok(_session('old', progress_age=None))]

    result = session_wait.wait_for_sessions_service(['old'], timeout_seconds=10)

    assert result['done'] is False
    assert result['sessions'][0]['outcome'] == 'running'
    assert 'only its end can be detected' in result['sessions'][0]['note']


def test_drafts_and_unknown_ids_settle_immediately(jesse):
    jesse.reads = [_ok(_session('d', 'draft', kind='optimization'), {'session_id': 'x', 'status': 'not_found'})]

    result = session_wait.wait_for_sessions_service(['d', 'x'])

    assert result['done'] is True and jesse.calls == 1
    assert result['sessions'][0]['note'].endswith('Start it with run_optimization.')
    assert result['sessions'][1]['outcome'] == 'not_found'


def test_the_timeout_returns_what_is_known_and_says_to_call_again(jesse):
    jesse.reads = [_ok(_session('a', progress={'percent': 12.0}))]

    result = session_wait.wait_for_sessions_service('a', timeout_seconds=30)

    assert result['done'] is False
    assert result['next'].startswith('Not done yet')
    assert result['sessions'][0]['progress'] == {'percent': 12.0}
    assert 27 <= result['waited_seconds'] <= 30
    assert session_wait.wait_for_sessions_service('a', timeout_seconds=0)['waited_seconds'] == 0


def test_a_read_failure_after_a_good_read_is_a_warning_not_an_error(jesse):
    down = {'status': 'error', 'error_type': 'connection_error', 'message': 'Could not connect to Jesse API'}
    jesse.reads = [_ok(_session('a')), down]

    result = session_wait.wait_for_sessions_service(['a'], timeout_seconds=9)

    assert result['status'] == 'success' and result['done'] is False
    assert 'Could not connect to Jesse API' in result['warning']


def test_never_reading_the_status_is_an_error(jesse):
    jesse.reads = [{'status': 'error', 'error_type': 'connection_error', 'message': 'Could not connect to Jesse API'}]

    result = session_wait.wait_for_sessions_service(['a'], timeout_seconds=6)

    assert result['status'] == 'error' and result['error_type'] == 'connection_error'


@pytest.mark.parametrize(('kwargs', 'message'), [
    ({'session_ids': []}, 'non-empty list'),
    ({'session_ids': '[1, 2]'}, 'non-empty list'),
    ({'session_ids': ['a'] * 1 + [str(i) for i in range(50)]}, 'At most 50'),
    ({'session_ids': ['a'], 'until': 'first'}, 'until must be'),
    ({'session_ids': ['a'], 'timeout_seconds': 900}, 'between 0 and 540'),
    ({'session_ids': ['a'], 'stall_minutes': 0}, 'at least 1'),
    ({'session_ids': ['a'], 'stall_minutes': '10'}, 'must be a number'),
])
def test_invalid_arguments_are_refused_before_waiting(jesse, kwargs, message):
    result = session_wait.wait_for_sessions_service(**kwargs)

    assert result['status'] == 'error' and message in result['message']
    assert jesse.calls == 0
