"""
The current status of several research sessions (backtest, optimization, Monte Carlo, significance
test) in one small read, for clients that wait on runs (the MCP's wait_for_sessions).

Each session is read through its model's normal by-id lookup, so a running session whose worker
this instance no longer has is reconciled exactly as on any other read (see
services/session_liveness.py). Only the fields needed to judge progress are returned.
"""

import uuid
from typing import Optional

from jesse.services import session_liveness

MAX_SESSION_IDS = 50
_ERROR_CHARS = 300


class StatusRequestError(Exception):
    error_type = 'invalid_request'
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _lookups() -> tuple:
    from jesse.models.BacktestSession import get_backtest_session_by_id
    from jesse.models.MonteCarloSession import get_monte_carlo_session_by_id
    from jesse.models.OptimizationSession import get_optimization_session_by_id
    from jesse.models.SignificanceTestSession import get_significance_test_session_by_id

    return (
        ('backtest', get_backtest_session_by_id),
        ('optimization', get_optimization_session_by_id),
        ('monte_carlo', get_monte_carlo_session_by_id),
        ('significance_test', get_significance_test_session_by_id),
    )


def lookup_session(kind: str, session_id: str):
    """A session by kind and id through its model's by-id read (which settles a lapsed lease)."""
    return dict(_lookups())[kind](session_id)


def _short_error(session) -> str:
    text = getattr(session, 'exception', None) or ''
    first_line = text.strip().splitlines()[0] if text.strip() else ''
    return first_line[:_ERROR_CHARS]


def _monte_carlo_progress(session_id: str) -> dict:
    from jesse.models.MonteCarloSession import MonteCarloCandlesSession, MonteCarloTradesSession

    progress = {}
    for name, part in (('trades', MonteCarloTradesSession), ('candles', MonteCarloCandlesSession)):
        row = part.get_or_none(part.monte_carlo_session_id == session_id)
        if row is not None:
            progress[name] = {'completed_scenarios': row.completed_scenarios, 'num_scenarios': row.num_scenarios,
                              'status': row.status}
            if not progress.get('error') and row.exception:
                progress['error'] = row.exception.strip().splitlines()[0][:_ERROR_CHARS]
    return progress


def _progress(kind: str, session) -> dict:
    if kind == 'optimization':
        return {'completed_trials': session.completed_trials, 'total_trials': session.total_trials}
    if kind == 'monte_carlo':
        return _monte_carlo_progress(str(session.id))
    # The percent is the last heartbeat's, so it only means something while the run goes on.
    if session.status == 'running' and session.progress is not None:
        return {'percent': session.progress}
    return {}


def _age_seconds(now_ms: int, then_ms) -> Optional[float]:
    return None if then_ms is None else round(max(0, now_ms - int(then_ms)) / 1000, 1)


def _describe(kind: str, session, now_ms: int) -> dict:
    progress = _progress(kind, session)
    part_error = progress.pop('error', '')
    error = _short_error(session) or part_error
    described = {
        'session_id': str(session.id),
        'session_type': kind,
        'status': session.status,
        # The machine that ran (or runs) it; None for a draft or a run by a version without leases.
        'claimed_by': session.claimed_by,
        'claimed_here': None if session.claimed_by is None else session.claimed_by == session_liveness.machine_label(),
        # The lease says whether a worker is alive; progress_at says when it last got further.
        'heartbeat_age_seconds': _age_seconds(now_ms, session.heartbeat_at),
        'progress_age_seconds': _age_seconds(now_ms, session.progress_at),
        'progress': progress,
    }
    if session.status == 'queued' or getattr(session, 'claim_id', None):
        # Queued for (or running on) a research runner: where, which attempt, how long it waited.
        from jesse.services import runner_queue
        queue = runner_queue.queue_info(str(session.id))
        if queue is not None:
            described['queue'] = queue
    if error:
        described['error'] = error
    return described


def get_statuses(session_ids: object) -> dict:
    """{'sessions': [...]} in the order asked; an unknown id is reported as status "not_found"."""
    if not isinstance(session_ids, list) or not session_ids:
        raise StatusRequestError('session_ids must be a non-empty list of session IDs.')
    if len(session_ids) > MAX_SESSION_IDS:
        raise StatusRequestError(f'At most {MAX_SESSION_IDS} session IDs per request.')

    now_ms = session_liveness.now_ms()
    sessions = []
    for session_id in session_ids:
        try:
            normalized = str(uuid.UUID(str(session_id)))
        except ValueError:
            sessions.append({'session_id': str(session_id), 'status': 'not_found', 'error': 'Not a session ID.'})
            continue
        for kind, lookup in _lookups():
            session = lookup(normalized)
            if session is not None:
                sessions.append(_describe(kind, session, now_ms))
                break
        else:
            sessions.append({'session_id': normalized, 'status': 'not_found'})
    return {'sessions': sessions, 'machine': session_liveness.machine_label(),
            'lease_seconds': session_liveness.LEASE_SECONDS}
