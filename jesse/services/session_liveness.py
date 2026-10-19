"""
Whether the worker of a research session (backtest, optimization, Monte Carlo, significance test)
is still alive, and how far it got. Works when several Jesse instances share one database.

Liveness is a lease. While a worker process is alive, the process manager that started it renews
the session's `heartbeat_at` every HEARTBEAT_INTERVAL_SECONDS. A `running` session whose lease is
older than LEASE_SECONDS has no live worker anywhere, so any instance reading it may mark it
stopped: no instance has to know which machine ran it. Times are taken from the database clock
(through a cached offset), so machines with different clocks agree.

Progress is separate: anything the worker publishes refreshes `progress_at` (and `progress`), so a
worker that is alive but stuck shows a fresh lease and an old `progress_at`. wait_for_sessions uses
that to report a stall.

- claim(): the start routes mark a session running before its worker starts; this starts its lease
  and progress clocks and records `claimed_by`, a label for the machine that runs it.
- renew_leases(): the process manager renews the leases of its live workers.
- lease_expired() / worker_is_gone(): the read paths stop a running session whose lease ran out.
- reconcile_exited_worker(): when a worker process exits while its session still says running
  (killed, out of memory, a lost database connection), its process manager marks it stopped with
  the exit code right away, instead of waiting for the lease.
- track() / beat(): a mode's worker names its session once; its progress updates refresh
  `progress_at` at most every HEARTBEAT_INTERVAL_SECONDS.

Rows written by versions without heartbeats have no `heartbeat_at`; they are judged as before.
"""

import socket
import time
import uuid
from typing import Iterable, Optional

import jesse.helpers as jh
from jesse.services.env import ENV_VALUES

HEARTBEAT_INTERVAL_SECONDS = 15
# Six missed renewals: long enough for a busy machine or a brief network drop, short enough that a
# dead machine's sessions are released within minutes.
LEASE_SECONDS = 90
CLOCK_REFRESH_SECONDS = 300

_KIND_BY_TRADING_MODE = {
    'backtest': 'backtest',
    'optimize': 'optimization',
    'monte-carlo': 'monte_carlo',
    'significance-test': 'significance_test',
}
_NAMES = {
    'backtest': 'backtest',
    'optimization': 'optimization',
    'monte_carlo': 'Monte Carlo',
    'significance_test': 'significance test',
}

_label: Optional[str] = None
_clock_offset_ms: Optional[int] = None
_clock_checked_at = 0.0
_tracked: Optional[tuple] = None
_last_beat = 0.0


def machine_label() -> str:
    """Which machine runs a session, for people and the dashboard: its host name and API port."""
    global _label
    if _label is None:
        _label = f"{socket.gethostname() or 'unknown-host'}:{ENV_VALUES.get('APP_PORT', '9000')}"
    return _label


def _database_now_ms() -> Optional[int]:
    from jesse.services.db import database

    if database.db is None:
        return None
    cursor = database.db.execute_sql('SELECT (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint')
    return int(cursor.fetchone()[0])


def now_ms() -> int:
    """The database clock in milliseconds (this machine's clock when the database cannot tell)."""
    global _clock_offset_ms, _clock_checked_at
    local = time.time() * 1000
    if _clock_offset_ms is None or time.monotonic() - _clock_checked_at > CLOCK_REFRESH_SECONDS:
        try:
            database_now = _database_now_ms()
            _clock_offset_ms = 0 if database_now is None else int(database_now - local)
        except Exception:
            _clock_offset_ms = _clock_offset_ms or 0
        _clock_checked_at = time.monotonic()
    return int(local + _clock_offset_ms)


def _models() -> dict:
    from jesse.models.BacktestSession import BacktestSession
    from jesse.models.MonteCarloSession import MonteCarloSession
    from jesse.models.OptimizationSession import OptimizationSession
    from jesse.models.SignificanceTestSession import SignificanceTestSession

    return {
        'backtest': BacktestSession,
        'optimization': OptimizationSession,
        'monte_carlo': MonteCarloSession,
        'significance_test': SignificanceTestSession,
    }


def claim(kind: str, session_id: str, mark_running: bool = False) -> None:
    """
    Start the session's lease and progress clocks on this machine; call it before starting the
    worker. `mark_running` also sets the status, for start routes that did not already.
    """
    if jh.is_unit_testing():
        return
    model = _models()[kind]
    now = now_ms()
    changes = {'claimed_by': machine_label(), 'heartbeat_at': now, 'progress_at': now, 'progress': None}
    if mark_running:
        changes.update(status='running', updated_at=now)
    model.update(**changes).where(model.id == session_id).execute()


def release_failed_start(kind: str, session_id: str, error: str) -> None:
    """Mark a claimed session stopped when its worker could not be started."""
    if jh.is_unit_testing():
        return
    model = _models()[kind]
    changes = {'status': 'stopped', 'updated_at': now_ms()}
    if 'exception' in model._meta.fields:
        changes['exception'] = error
    model.update(**changes).where(model.id == session_id).execute()


def _session_ids(client_ids: Iterable[str]) -> list:
    ids = []
    for client_id in client_ids:
        try:
            ids.append(str(uuid.UUID(str(client_id))))
        except ValueError:
            continue
    return ids


def renew_leases(client_ids: Iterable[str]) -> None:
    """Renew the lease of every running research session among these live workers."""
    ids = _session_ids(client_ids)
    if not ids or jh.is_unit_testing():
        return
    now = now_ms()
    for model in _models().values():
        model.update(heartbeat_at=now).where(model.id.in_(ids) & (model.status == 'running')).execute()


def lease_expired(session) -> bool:
    heartbeat_at = getattr(session, 'heartbeat_at', None)
    return heartbeat_at is not None and now_ms() - int(heartbeat_at) > LEASE_SECONDS * 1000


def has_live_worker(session) -> bool:
    """Whether the session is running with a live worker (so starting it again would duplicate it)."""
    if getattr(session, 'status', None) != 'running' or jh.is_unit_testing():
        return False
    if getattr(session, 'heartbeat_at', None) is not None:
        return not lease_expired(session)
    from jesse.services.redis import is_process_active

    return is_process_active(str(session.id))


def worker_is_gone(session, legacy_coordinator_check: bool = True) -> bool:
    """
    Whether a `running` session has no live worker: its lease ran out. A row without a lease
    (written by a version without heartbeats) is judged by this instance's coordinator when
    `legacy_coordinator_check` is set, as Jesse always did for optimizations, Monte Carlo and
    significance tests.
    """
    if getattr(session, 'status', None) != 'running' or jh.is_unit_testing():
        return False
    if getattr(session, 'heartbeat_at', None) is not None:
        return lease_expired(session)
    if not legacy_coordinator_check:
        return False
    from jesse.services.redis import is_process_active

    return not is_process_active(str(session.id))


def reconcile_exited_worker(client_id: str, exit_code: Optional[int]) -> list:
    """
    Stop the sessions that still say `running` after the worker this machine started for them
    exited. Returns the kinds that were stopped (normally none: a worker reports its own end).
    """
    if jh.is_unit_testing():
        return []
    from jesse.services.redis import is_process_active

    # A rerun of the same session may already have a new worker here.
    if is_process_active(client_id):
        return []
    stopped = []
    for kind, model in _models().items():
        try:
            reason = (
                f'The {_NAMES[kind]} worker exited (exit code {exit_code}) without reporting a result. '
                'It may have been killed, run out of memory, or lost its database connection.'
            )
            changes = {'status': 'stopped', 'updated_at': now_ms()}
            if 'exception' in model._meta.fields:
                changes['exception'] = reason
            # Only a run this machine claimed: if another machine took the session over since,
            # this worker's exit says nothing about that run.
            claimed_here = (model.claimed_by == machine_label()) | model.claimed_by.is_null()
            updated = model.update(**changes).where(
                (model.id == client_id) & (model.status == 'running') & claimed_here
            ).execute()
        except Exception:
            # Not a session of this kind (or its id is not a UUID); nothing to reconcile.
            continue
        if updated:
            stopped.append(kind)
            if kind == 'monte_carlo':
                _stop_monte_carlo_parts(client_id, reason)
    return stopped


def _stop_monte_carlo_parts(session_id: str, reason: str) -> None:
    from jesse.models.MonteCarloSession import MonteCarloCandlesSession, MonteCarloTradesSession

    for part in (MonteCarloTradesSession, MonteCarloCandlesSession):
        part.update(status='stopped', exception=reason, updated_at=now_ms()).where(
            (part.monte_carlo_session_id == session_id) & (part.status == 'running')
        ).execute()


def claimed_here_clause(model):
    """Rows this machine runs (or rows from versions that did not record it), for 'running here' lookups."""
    return (model.claimed_by == machine_label()) | model.claimed_by.is_null()


def track(trading_mode: str, session_id: str) -> None:
    """Name the session whose progress this worker process reports."""
    global _tracked, _last_beat
    kind = _KIND_BY_TRADING_MODE.get(trading_mode)
    _tracked = (kind, session_id) if kind else None
    _last_beat = 0.0


def beat(progress: Optional[float] = None) -> None:
    """Record the tracked session's progress, at most every HEARTBEAT_INTERVAL_SECONDS. Never raises."""
    global _last_beat
    if _tracked is None or jh.is_unit_testing():
        return
    now = time.monotonic()
    if now - _last_beat < HEARTBEAT_INTERVAL_SECONDS:
        return
    _last_beat = now
    kind, session_id = _tracked
    try:
        model = _models()[kind]
        changes = {'progress_at': now_ms()}
        if isinstance(progress, (int, float)) and not isinstance(progress, bool):
            changes['progress'] = float(progress)
        # A session that already ended (or was reconciled) is not brought back to life.
        model.update(**changes).where((model.id == session_id) & (model.status == 'running')).execute()
    except Exception:
        pass
