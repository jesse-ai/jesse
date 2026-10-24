"""
Research runners: run backtests, optimizations, Monte Carlo runs and significance tests on other
machines that share this database.

One machine is the hub (RESEARCH_RUNNERS=true in its .env): the dashboard and the MCP agent talk
to it. A run started with `where` other than "local" is not started on the hub; it is queued as
a RunnerJob that carries the worker call and the job's code (services/code_bundle.py). Runners
(`jesse runner`, or `jesse run` with RUNNER_CORES) take queued jobs from the database, run them in
their own process manager and write results to the same tables, so the hub's dashboard shows them.

- Waking up: queuing sends NOTIFY on CHANNEL_JOBS; runners LISTEN, and also check the queue
  every few seconds in case they missed it.
- Claiming: a runner takes the oldest job it may run with FOR UPDATE SKIP LOCKED, so two runners
  never take the same one. Each claim gets a claim_id that the worker's session writes require
  (session_liveness.fenced), so a runner that lost its job cannot overwrite the new run.
- Liveness: the runner's process manager renews the session lease (session_liveness). When a
  lease lapses (the runner died or lost its network), the job goes back to the queue, up to
  max_attempts claims; a worker that crashes is not retried.
- Cancelling: process_manager.cancel_process calls cancel(): a queued job is dropped, a running
  one is signalled to its runner on CHANNEL_CANCEL.

Turned off (no RESEARCH_RUNNERS on the hub), every start route runs locally exactly as before.
"""

import json
import uuid
from typing import Callable, Optional

import jesse.helpers as jh
from jesse.services import code_bundle, machine_stats, session_liveness
from jesse.services.env import ENV_VALUES

CHANNEL_JOBS = 'jesse_runner_jobs'
CHANNEL_CANCEL = 'jesse_runner_cancel'
CHANNEL_FILES = 'jesse_runner_files'
RUNNER_ALIVE_SECONDS = 45
LOCAL = 'local'
ANY = 'any'
AUTO = 'auto'
FUNCTIONS = ('backtest', 'optimization', 'monte_carlo', 'significance_test')
_KIND_NAMES = {'backtest': 'backtest', 'optimization': 'optimization', 'monte_carlo': 'Monte Carlo',
               'significance_test': 'significance test'}


class QueueError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _truthy(value) -> bool:
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def enabled() -> bool:
    """Whether this instance is a hub that may queue runs for runners."""
    return _truthy(ENV_VALUES.get('RESEARCH_RUNNERS', ''))


def placement() -> Optional[str]:
    """
    The hub's RUNNER_ORDER: runner names in order of preference, comma-separated. A job goes to
    the first listed runner with room for it; "*" stands for any other runner. Unset means any
    runner, first come first served. Examples: "macmini,macbook" (the mini first, the hub when the
    mini is full), "macmini" (only the mini), "macmini,*" (the mini first, then anyone).
    """
    names = [name.strip() for name in str(ENV_VALUES.get('RUNNER_ORDER') or '').split(',') if name.strip()]
    return ','.join(dict.fromkeys(names)) or None


def _rank(order: Optional[str], name: str) -> Optional[int]:
    """A runner's place in a job's order (lower runs first), or None when it may not run it."""
    if not order:
        return 0
    names = order.split(',')
    if name in names:
        return names.index(name)
    return names.index('*') if '*' in names else None


def max_attempts() -> int:
    try:
        return max(1, int(ENV_VALUES.get('RUNNER_MAX_ATTEMPTS', 3)))
    except ValueError:
        return 3


def jesse_version() -> str:
    from jesse.version import __version__
    return __version__


def _models():
    from jesse.models.RunnerJob import CodeBlob, Runner, RunnerFile, RunnerJob
    return RunnerJob, Runner, CodeBlob, RunnerFile


def _database():
    """The database the queue tables are bound to (Jesse's own handle is reset after migrations)."""
    RunnerJob, _, _, _ = _models()
    return RunnerJob._meta.database


def notify(channel: str, payload: str = '') -> None:
    try:
        _database().execute_sql('SELECT pg_notify(%s, %s)', (channel, payload))
    except Exception:
        # Runners also check the queue on a timer; a missed wake-up only delays a start.
        pass


def live_runners() -> list:
    """Runners that are connected, take jobs (a core budget above 0) and run this hub's Jesse version."""
    _, Runner, _, _ = _models()
    cutoff = session_liveness.now_ms() - RUNNER_ALIVE_SECONDS * 1000
    return list(Runner.select().where((Runner.last_seen >= cutoff) & (Runner.cores_budget > 0)
                                      & (Runner.jesse_version == jesse_version())).order_by(Runner.name))


def resolve_target(where: Optional[str]) -> tuple:
    """
    ('local', None) to start here, or ('queue', target) with target None for any runner.
    `where`: None or "local" (the default), "auto" (queue when runners are on and one is alive),
    "any", or a runner name.
    """
    value = (where or LOCAL).strip()
    if value == LOCAL:
        return LOCAL, None
    if value == AUTO:
        if not enabled():
            return LOCAL, None
        if placement():
            # RUNNER_ORDER says where research runs; waiting for those runners beats running here.
            return 'queue', None
        return ('queue', None) if live_runners() else (LOCAL, None)
    if not enabled():
        raise QueueError('Research runners are not turned on for this Jesse. Set RESEARCH_RUNNERS=true in '
                         'its .env and restart it, or run with where="local".')
    if value == ANY:
        return 'queue', None
    _, Runner, _, _ = _models()
    if Runner.get_or_none(Runner.name == value) is None:
        known = ', '.join(r.name for r in Runner.select().order_by(Runner.name)) or 'none yet'
        raise QueueError(f'No runner is named "{value}". Known runners: {known}.')
    return 'queue', value


def _session_model(kind: str):
    return session_liveness._models()[kind]


def mark_session_queued(kind: str, session_id: str) -> None:
    model = _session_model(kind)
    model.update(status='queued', claimed_by=None, claim_id=None, heartbeat_at=None, progress_at=None,
                 progress=None, updated_at=session_liveness.now_ms()).where(model.id == session_id).execute()


# Position of the cpu_cores argument of the modes that use several cores.
CPU_CORES_ARGUMENT = {'optimization': 11, 'monte_carlo': 11}


def job_cores(function: str, arguments: list) -> int:
    """The CPU cores a job uses: its cpu_cores for an optimization or Monte Carlo run, else 1."""
    position = CPU_CORES_ARGUMENT.get(function)
    if position is None:
        return 1
    value = arguments[position] if len(arguments) > position else None
    if not isinstance(value, int) or isinstance(value, bool):
        config = arguments[1] if len(arguments) > 1 and isinstance(arguments[1], dict) else {}
        value = config.get('cpu_cores')
    return max(1, int(value)) if isinstance(value, int) and not isinstance(value, bool) else 1


def enqueue(kind: str, function: str, arguments: list, strategy_names: list, target: Optional[str]) -> str:
    """Queue a session's run for a runner; the session shows as queued until one claims it."""
    if function not in FUNCTIONS:
        raise ValueError(f'Unknown runner function: {function}')
    RunnerJob, _, _, _ = _models()
    session_id = str(arguments[0])
    if RunnerJob.select().where((RunnerJob.session_id == session_id) & (RunnerJob.status == 'running')).exists():
        raise QueueError(f'This {_KIND_NAMES[kind]} session is already running on a runner.', 409)
    try:
        bundle = code_bundle.build(strategy_names)
    except code_bundle.BundleError as e:
        raise QueueError(str(e))
    now = session_liveness.now_ms()
    manifest = code_bundle.store(bundle, now)
    # A session has one active job: queuing it again replaces a job that was still waiting.
    RunnerJob.update(status='cancelled', finished_at=now).where(
        (RunnerJob.session_id == session_id) & (RunnerJob.status == 'queued')).execute()
    job_id = str(uuid.uuid4())
    RunnerJob.insert(
        id=job_id, session_id=session_id, kind=kind, status='queued', function=function,
        cores=job_cores(function, arguments),
        arguments=json.dumps(arguments), code_manifest=json.dumps(manifest),
        packages=json.dumps(bundle['packages']), target=target, placement=None if target else placement(),
        jesse_version=jesse_version(),
        attempt=0, max_attempts=max_attempts(), queued_at=now,
    ).execute()
    mark_session_queued(kind, session_id)
    notify(CHANNEL_JOBS, target or '')
    return job_id


_CLAIM_COLUMNS = ('id', 'session_id', 'kind', 'function', 'arguments', 'code_manifest', 'packages', 'attempt',
                  'max_attempts', 'cores')


def _capacity() -> dict:
    """{name: {'budget', 'free'}} of the live, compatible runners, from their last heartbeat."""
    return {runner.name: {'budget': runner.cores_budget, 'free': max(0, runner.cores_budget - runner.cores_used)}
            for runner in live_runners()}


def _allowed(job: dict, runner_name: str) -> bool:
    if job['target'] is not None:
        return job['target'] == runner_name
    if f',{runner_name},' in (job['excluded'] or ''):
        return False
    return _rank(job['placement'], runner_name) is not None


def _cost(job: dict, budget: int) -> int:
    return max(1, min(int(job['cores'] or 1), budget))


def _candidates(job: dict, runners: dict) -> list:
    """
    The runners that may run the job: those allowed by its target and RUNNER_ORDER and, when any of
    them can give it all the cores it asked for, only those. A job is capped to a smaller runner's
    budget only when no connected runner is big enough, so its cpu_cores is never cut just because
    a smaller machine happened to be free.
    """
    allowed = [name for name in runners if _allowed(job, name)]
    big_enough = [name for name in allowed if runners[name]['budget'] >= int(job['cores'] or 1)]
    return big_enough or allowed


def _reserver(job: dict, runners: dict) -> Optional[str]:
    """
    The one runner that waits for this job when no runner has room for it yet: the first in the
    job's RUNNER_ORDER, else the one with the most cores. The others keep working on newer jobs.
    """
    candidates = _candidates(job, runners)
    if not candidates:
        return None
    return min(candidates, key=lambda name: (_rank(job['placement'], name), -runners[name]['budget'], name))


def _choose(waiting: list, runner_name: str, budget: int, free: int, runners: dict) -> tuple:
    """
    Pick the job this runner should start, walking the queue oldest first: ('claim', job) to start
    it now, ('wait', job) to start nothing until this runner has room for a job it reserves, or
    (None, None).

    - Only runners that can give a job all its cores take it (see _candidates).
    - A job goes to the best-ranked of them that has room for it now (its RUNNER_ORDER rank, then
      first come); the walk counts those cores as used, so each runner gets as many jobs as it has
      room for.
    - When none of them has room yet, its reserving runner (_reserver) starts nothing newer until
      enough of its own cores are free, so a big job is never overtaken by small ones there; the
      other runners keep taking newer jobs.
    """
    everyone = {name: dict(capacity) for name, capacity in runners.items()}
    everyone[runner_name] = {'budget': budget, 'free': free}
    for job in waiting:
        candidates = _candidates(job, everyone)
        # Runners with room for it now, best-ranked first (a runner holding for a big job has none).
        with_room = sorted(
            (_rank(job['placement'], name), name) for name in candidates
            if everyone[name]['free'] >= _cost(job, everyone[name]['budget'])
        )
        if runner_name in candidates:
            my_rank = _rank(job['placement'], runner_name)
            if (my_rank, runner_name) in with_room and not any(rank < my_rank for rank, _ in with_room):
                return 'claim', job
        if with_room:
            # Another runner takes it: count its cores as used for the rest of this walk.
            taker = next(name for _, name in with_room if name != runner_name)
            everyone[taker]['free'] -= _cost(job, everyone[taker]['budget'])
            continue
        if not candidates:
            continue
        reserver = _reserver(job, everyone)
        if reserver == runner_name:
            return 'wait', job
        # The reserving runner starts nothing newer until this job fits there.
        everyone[reserver]['free'] = -1
    return None, None


def claim_next(runner_name: str, free_cores: int, budget: int) -> Optional[dict]:
    """
    Take the job this runner should start now under the queue order, targets, the hub's
    RUNNER_ORDER and core budgets, or None (nothing fits, or it waits for a job it reserves).
    """
    if budget <= 0:
        return None
    RunnerJob, _, _, _ = _models()
    waiting = list(RunnerJob.select(RunnerJob.id, RunnerJob.target, RunnerJob.placement, RunnerJob.excluded,
                                    RunnerJob.cores)
                   .where((RunnerJob.status == 'queued') & (RunnerJob.jesse_version == jesse_version()))
                   .order_by(RunnerJob.queued_at).limit(200).dicts())
    if not waiting:
        return None
    runners = _capacity()
    for _ in range(len(waiting)):
        decision, candidate = _choose(waiting, runner_name, budget, free_cores, runners)
        if decision != 'claim':
            return None
        claim_id = str(uuid.uuid4())
        cursor = _database().execute_sql(
            """
            UPDATE runnerjob SET status = 'running', claim_id = %s, claimed_by = %s, attempt = attempt + 1,
                   claimed_at = %s
            WHERE id = (SELECT id FROM runnerjob WHERE id = %s AND status = 'queued' FOR UPDATE SKIP LOCKED)
            RETURNING id, session_id, kind, function, arguments, code_manifest, packages, attempt, max_attempts, cores
            """,
            (claim_id, runner_name, session_liveness.now_ms(), str(candidate['id'])),
        )
        row = cursor.fetchone()
        if row is None:
            # Another runner took it a moment ago: decide again without it.
            waiting = [job for job in waiting if job['id'] != candidate['id']]
            continue
        job = dict(zip(_CLAIM_COLUMNS, row))
        job['id'], job['session_id'] = str(job['id']), str(job['session_id'])
        job['arguments'] = json.loads(job['arguments'])
        job['code_manifest'] = json.loads(job['code_manifest'])
        job['packages'] = json.loads(job['packages'] or '[]')
        job['claim_id'] = claim_id
        job['cost'] = _cost(job, budget)
        return job
    return None


def release(job: dict, runner_name: str, reason: str) -> None:
    """Give a claimed job back (this runner cannot run it), keeping it from this runner."""
    RunnerJob, _, _, _ = _models()
    current = RunnerJob.get_or_none(RunnerJob.id == job['id'])
    if current is None or current.claim_id != job['claim_id']:
        return
    excluded = (current.excluded or ',') + f'{runner_name},'
    still_able = [r for r in live_runners() if f',{r.name},' not in excluded
                  and (current.target == r.name if current.target else _rank(current.placement, r.name) is not None)]
    if not still_able:
        _fail(current, f'No runner can run this job. Last: {reason}')
        return
    RunnerJob.update(status='queued', claim_id=None, claimed_by=None, attempt=RunnerJob.attempt - 1,
                     excluded=excluded, error=reason).where(RunnerJob.id == job['id']).execute()
    mark_session_queued(current.kind, str(current.session_id))
    notify(CHANNEL_JOBS, current.target or '')


def requeue(job: dict, reason: str) -> None:
    """Put a claimed job back in the queue without counting the claim (its runner is shutting down)."""
    RunnerJob, _, _, _ = _models()
    current = RunnerJob.get_or_none(RunnerJob.id == job['id'])
    if current is None or current.claim_id != job['claim_id'] or current.status != 'running':
        return
    RunnerJob.update(status='queued', claim_id=None, claimed_by=None, attempt=RunnerJob.attempt - 1,
                     error=reason).where(RunnerJob.id == job['id']).execute()
    mark_session_queued(current.kind, str(current.session_id))
    notify(CHANNEL_JOBS, current.target or '')


def fail(job: dict, reason: str) -> None:
    """Fail a claimed job that cannot be run anywhere (its code could not be restored, say)."""
    RunnerJob, _, _, _ = _models()
    current = RunnerJob.get_or_none(RunnerJob.id == job['id'])
    if current is not None and current.claim_id == job['claim_id']:
        _fail(current, reason)


def _fail(job, reason: str) -> None:
    RunnerJob, _, _, _ = _models()
    now = session_liveness.now_ms()
    RunnerJob.update(status='failed', error=reason, finished_at=now).where(RunnerJob.id == job.id).execute()
    model = _session_model(job.kind)
    changes = {'status': 'stopped', 'updated_at': now}
    if 'exception' in model._meta.fields:
        changes['exception'] = reason
    model.update(**changes).where((model.id == job.session_id) & (model.status.in_(['queued', 'running']))).execute()


def finish(job_id: str, claim_id: str, session_status: Optional[str], error: Optional[str] = None) -> None:
    """Record the end of a job its runner ran to completion (or that crashed)."""
    RunnerJob, _, _, _ = _models()
    status = 'done' if session_status in ('finished', 'stopped', 'cancelled', 'terminated') and not error else 'failed'
    RunnerJob.update(status=status, error=error, finished_at=session_liveness.now_ms()).where(
        (RunnerJob.id == job_id) & (RunnerJob.claim_id == claim_id) & (RunnerJob.status == 'running')
    ).execute()


def settle_lapsed(kind: str, session, stop: Callable[[], None]) -> str:
    """
    A running session's lease ran out. A runner job goes back to the queue while it has claims
    left; anything else is stopped with `stop()`. Returns the session's new status.
    """
    RunnerJob, _, _, _ = _models()
    job = None
    claim_id = getattr(session, 'claim_id', None)
    if claim_id:
        try:
            job = RunnerJob.get_or_none((RunnerJob.session_id == session.id) & (RunnerJob.claim_id == claim_id)
                                        & (RunnerJob.status == 'running'))
        except Exception:
            job = None
    if job is None:
        stop()
        return 'stopped'
    if job.attempt >= job.max_attempts:
        _fail(job, f'Lost its runner ({job.claimed_by}) {job.attempt} times; giving up. '
                   'Check that runner machines stay connected to the database.')
        return 'stopped'
    requeued = RunnerJob.update(status='queued', claim_id=None, claimed_by=None,
                                error=f'Runner {job.claimed_by} stopped answering; queued again.').where(
        (RunnerJob.id == job.id) & (RunnerJob.claim_id == claim_id)).execute()
    if requeued:
        mark_session_queued(kind, str(session.id))
        notify(CHANNEL_JOBS, job.target or '')
    return 'queued'


def cancel(session_id: str) -> None:
    """Drop a queued job, or signal the runner of a running one (called by cancel_process)."""
    if jh.is_unit_testing():
        return
    try:
        RunnerJob, _, _, _ = _models()
        jobs = list(RunnerJob.select().where((RunnerJob.session_id == session_id)
                                             & (RunnerJob.status.in_(['queued', 'running']))))
    except Exception:
        return
    now = session_liveness.now_ms()
    for job in jobs:
        RunnerJob.update(status='cancelled', finished_at=now).where(RunnerJob.id == job.id).execute()
        if job.status == 'queued':
            model = _session_model(job.kind)
            model.update(status='cancelled', updated_at=now).where(
                (model.id == session_id) & (model.status == 'queued')).execute()
        elif job.claimed_by != session_liveness.machine_label():
            notify(CHANNEL_CANCEL, str(session_id))


def queue_info(session_id: str) -> Optional[dict]:
    """The session's latest job, for status reads (None when it was never queued)."""
    RunnerJob, _, _, _ = _models()
    job = (RunnerJob.select().where(RunnerJob.session_id == session_id)
           .order_by(RunnerJob.queued_at.desc()).first())
    if job is None:
        return None
    info = {'job_status': job.status, 'target': job.target or ANY, 'attempt': job.attempt,
            'queued_age_seconds': round(max(0, session_liveness.now_ms() - job.queued_at) / 1000, 1)}
    if job.error:
        info['note'] = job.error
    if job.excluded:
        info['excluded_runners'] = [name for name in job.excluded.split(',') if name]
    return info


def runners_payload() -> dict:
    RunnerJob, Runner, _, _ = _models()
    now = session_liveness.now_ms()
    running = {}
    for job in RunnerJob.select().where(RunnerJob.status == 'running'):
        running.setdefault(job.claimed_by, []).append({'session_id': str(job.session_id), 'session_type': job.kind})
    runners = []
    for runner in Runner.select().order_by(Runner.name):
        age = round(max(0, now - runner.last_seen) / 1000, 1)
        runners.append({
            'name': runner.name, 'role': runner.role, 'host': runner.host, 'alive': age <= RUNNER_ALIVE_SECONDS,
            'last_seen_seconds_ago': age, 'cores_budget': runner.cores_budget, 'cores_used': runner.cores_used,
            'cores_free': max(0, runner.cores_budget - runner.cores_used) if age <= RUNNER_ALIVE_SECONDS else 0,
            'cpu_cores': runner.cpu_cores, 'cpu_percent': runner.cpu_percent, 'load_1m': runner.load_1m,
            'memory_total_gb': machine_stats.gigabytes(runner.memory_total_bytes),
            'memory_used_gb': machine_stats.gigabytes(runner.memory_used_bytes),
            'memory_percent': (round(runner.memory_used_bytes / runner.memory_total_bytes * 100, 1)
                               if runner.memory_used_bytes is not None and runner.memory_total_bytes else None),
            'jesse_version': runner.jesse_version,
            'compatible': runner.jesse_version == jesse_version(),
            'running': running.get(runner.name, []),
        })
    queued = RunnerJob.select().where(RunnerJob.status == 'queued').count()
    return {'enabled': enabled(), 'hub_jesse_version': jesse_version(), 'runner_order': placement() or '*',
            'queued_jobs': queued, 'runners': runners}


def sweep() -> None:
    """Housekeeping any runner (or the hub) runs now and then: lapsed jobs, unused code, old rows."""
    RunnerJob, Runner, CodeBlob, _ = _models()
    from jesse.services.session_status import lookup_session

    for job in list(RunnerJob.select().where(RunnerJob.status == 'running')):
        # Reading a session through its model settles a lapsed lease (settle_lapsed above).
        lookup_session(job.kind, str(job.session_id))

    now = session_liveness.now_ms()
    in_use = set()
    for job in RunnerJob.select(RunnerJob.code_manifest).where(RunnerJob.status.in_(['queued', 'running'])):
        in_use.update(json.loads(job.code_manifest).values())
    old = now - 3 * 24 * 3600 * 1000
    stale = [blob.hash for blob in CodeBlob.select(CodeBlob.hash).where(CodeBlob.last_used_at < old)
             if blob.hash not in in_use]
    if stale:
        CodeBlob.delete().where(CodeBlob.hash.in_(stale)).execute()
    RunnerJob.delete().where(RunnerJob.status.in_(['done', 'cancelled', 'failed'])
                             & (RunnerJob.finished_at < now - 30 * 24 * 3600 * 1000)).execute()
    Runner.delete().where(Runner.last_seen < now - 7 * 24 * 3600 * 1000).execute()


def queue_if_requested(kind: str, function: str, arguments, routes, where: Optional[str]) -> Optional[dict]:
    """
    For a start route: queue the run for a runner when `where` asks for it and return the
    response to send; None means start it here as usual. Raises QueueError for a bad `where`.
    """
    mode, target = resolve_target(where)
    if mode == LOCAL:
        return None
    strategies = [route['strategy'] if isinstance(route, dict) else getattr(route, 'strategy') for route in routes]
    job_id = enqueue(kind, function, list(arguments), strategies, target)
    alive = [runner.name for runner in live_runners()
             if target is None or runner.name == target]
    response = {
        'status': 'queued', 'session_id': str(arguments[0]), 'job_id': job_id, 'target': target or ANY,
        'message': f'Queued for {"runner " + target if target else "any runner"}.',
    }
    if not alive:
        response['warning'] = ('No runner that can take it is connected right now; it starts when one is.')
    return response
