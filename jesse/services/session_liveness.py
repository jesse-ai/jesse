"""
Which Jesse instance owns a research session (backtest, optimization, Monte Carlo, significance
test), and whether its worker is still alive.

Several Jesse instances can share one database (for example research machines that all point at
the same PostgreSQL), but each instance's coordinator only knows its own workers. So a session row
records its `owner`, the instance that started it, and a `heartbeat_at` that its worker refreshes
while it runs. Only the owner may conclude from its coordinator that a `running` session has no
worker; another instance reading the same row leaves it alone.

- claim(): the start endpoints mark a session running and owned here before its worker starts.
- worker_is_gone(): the read paths reconcile a `running` row whose worker this instance no longer
  has. A just-claimed session gets a grace period, since its worker marker may not exist yet.
- reconcile_exited_worker(): the process manager calls it when a worker process exits, so a worker
  that died without reporting (killed, out of memory, a lost database connection) leaves a
  `stopped` session with a reason instead of a `running` one forever.
- track() / beat(): a mode's worker names its session once, and its progress updates refresh the
  heartbeat at most every HEARTBEAT_INTERVAL_SECONDS.

Rows written before these columns existed have no owner; they are reconciled as before.
"""

import socket
import time
from typing import Optional

import jesse.helpers as jh
from jesse.services.env import ENV_VALUES

HEARTBEAT_INTERVAL_SECONDS = 15
# A claimed session is not reconciled for this long without a heartbeat, which covers the moment
# between marking it running and its worker publishing its coordinator marker.
CLAIM_GRACE_MS = 60_000

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

_owner: Optional[str] = None
_tracked: Optional[tuple] = None
_last_beat = 0.0


def instance_owner() -> str:
    """This Jesse instance: its host name and API port."""
    global _owner
    if _owner is None:
        _owner = f"{socket.gethostname() or 'unknown-host'}:{ENV_VALUES.get('APP_PORT', '9000')}"
    return _owner


def _now_ms() -> int:
    return int(time.time() * 1000)


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
    Record that this instance runs the session from now on; call it before starting the worker.
    `mark_running` also sets the status, for start routes that did not already.
    """
    if jh.is_unit_testing():
        return
    model = _models()[kind]
    changes = {'owner': instance_owner(), 'heartbeat_at': _now_ms(), 'progress': None}
    if mark_running:
        changes.update(status='running', updated_at=_now_ms())
    model.update(**changes).where(model.id == session_id).execute()


def release_failed_start(kind: str, session_id: str, error: str) -> None:
    """Mark a claimed session stopped when its worker could not be started."""
    if jh.is_unit_testing():
        return
    model = _models()[kind]
    changes = {'status': 'stopped', 'updated_at': _now_ms()}
    if 'exception' in model._meta.fields:
        changes['exception'] = error
    model.update(**changes).where(model.id == session_id).execute()


def has_live_worker(session) -> bool:
    """Whether the session is running with a worker on this instance (so starting it again would duplicate it)."""
    if getattr(session, 'status', None) != 'running' or jh.is_unit_testing():
        return False
    from jesse.services.redis import is_process_active

    return is_process_active(str(session.id))


def is_owned_here(session, allow_unowned: bool = True) -> bool:
    owner = getattr(session, 'owner', None)
    if owner is None:
        return allow_unowned
    return owner == instance_owner()


def owned_here_clause(model):
    """A query condition for the rows this instance may reconcile."""
    return (model.owner == instance_owner()) | model.owner.is_null()


def worker_is_gone(session, allow_unowned: bool = True) -> bool:
    """
    Whether a `running` session belongs to this instance and its worker no longer exists.
    `allow_unowned` also judges rows without an owner (written before owners existed) by this
    instance's coordinator, as Jesse always did for optimizations, Monte Carlo and significance tests.
    """
    if getattr(session, 'status', None) != 'running' or jh.is_unit_testing() or not is_owned_here(session, allow_unowned):
        return False
    heartbeat_at = getattr(session, 'heartbeat_at', None)
    if heartbeat_at is not None and _now_ms() - int(heartbeat_at) < CLAIM_GRACE_MS:
        return False

    from jesse.services.redis import is_process_active

    return not is_process_active(str(session.id))


def reconcile_exited_worker(client_id: str, exit_code: Optional[int]) -> list:
    """
    Stop the sessions this instance owns that still say `running` after their worker exited.
    Returns the kinds that were stopped (normally none: a worker reports its own end).
    """
    if jh.is_unit_testing():
        return []
    from jesse.services.redis import is_process_active

    # A rerun of the same session may already have a new worker.
    if is_process_active(client_id):
        return []
    stopped = []
    for kind, model in _models().items():
        try:
            reason = (
                f'The {_NAMES[kind]} worker exited (exit code {exit_code}) without reporting a result. '
                'It may have been killed, run out of memory, or lost its database connection.'
            )
            changes = {'status': 'stopped', 'updated_at': _now_ms()}
            if 'exception' in model._meta.fields:
                changes['exception'] = reason
            updated = model.update(**changes).where(
                (model.id == client_id) & (model.status == 'running') & owned_here_clause(model)
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
        part.update(status='stopped', exception=reason, updated_at=_now_ms()).where(
            (part.monte_carlo_session_id == session_id) & (part.status == 'running')
        ).execute()


def track(trading_mode: str, session_id: str) -> None:
    """Name the session whose heartbeat this worker process refreshes."""
    global _tracked, _last_beat
    kind = _KIND_BY_TRADING_MODE.get(trading_mode)
    _tracked = (kind, session_id) if kind else None
    _last_beat = 0.0


def beat(progress: Optional[float] = None) -> None:
    """Refresh the tracked session's heartbeat, at most every HEARTBEAT_INTERVAL_SECONDS. Never raises."""
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
        changes = {'heartbeat_at': _now_ms()}
        if isinstance(progress, (int, float)) and not isinstance(progress, bool):
            changes['progress'] = float(progress)
        # A session that already ended (or was reconciled) is not brought back to life.
        model.update(**changes).where((model.id == session_id) & (model.status == 'running')).execute()
    except Exception:
        pass
