"""
Background Python jobs started by MCP assistants.

This module owns the process management shared by two separately scoped job kinds:

- Research jobs run `<this Python interpreter> research_scripts/<path>.py <args...>` from the
  project root (the Jesse research module finds `.env`, `strategies/`, and `storage/` from
  there). Their records live in storage/research-jobs/<job_id>.json and their combined
  stdout/stderr in storage/logs/research-scripts/<job_id>.txt.
- Temporary analysis jobs (jesse.services.analysis_jobs) run generated code inside their own
  workspace under storage/mcp/analysis/<job_id>/ and keep their record and output there.

Every job runs without a shell, in its own process group, so cancelling, timing out, or
shutting Jesse down also stops any processes it started. Each kind has its own concurrency
limit, so analysis jobs never block research jobs or the other way round.

The code is NOT sandboxed. It runs as the same OS user, with the same environment variables,
filesystem and network access as the Jesse process, so it can read `.env`, credentials in
the database, and any file that user can read. The path checks here only decide which file
is started; they do not limit what the started code does.

Running jobs are tracked in this process; a record still marked running when no job in this
process owns it (Jesse restarted) is reported as interrupted. After a normal shutdown the
job was stopped. After a crash (SIGKILL) Jesse cannot stop it: the orphaned process keeps
running untracked, with no deadline enforced, until it exits on its own.
"""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional
from uuid import uuid4

from jesse.services.project_files import (
    RESEARCH_SCRIPTS_ROOT,
    ProjectFileError,
    display_path,
    open_regular_file,
    parse_path,
)

JOBS_DIR = os.path.join('storage', 'research-jobs')
LOGS_DIR = os.path.join('storage', 'logs', 'research-scripts')

# Research scripts commonly use every CPU core (optimization, model training) and a lot of
# memory. Two at once still lets an assistant run a quick script beside a long one without
# starving the dashboard, backtests, or live sessions running in the same Jesse process.
MAX_CONCURRENT_JOBS = 2
# Every job has a deadline so a forgotten or hung script cannot run forever. One hour covers
# typical data gathering and training runs; twelve hours allows an overnight run.
DEFAULT_TIMEOUT_MINUTES = 60
MAX_TIMEOUT_MINUTES = 12 * 60
# Arguments are for options such as symbols, dates, and output names, not for data.
MAX_ARGS = 64
MAX_ARG_LENGTH = 4096
# Output beyond this is discarded (and flagged) so a chatty script cannot fill the disk.
MAX_LOG_BYTES = 20 * 1024 * 1024
# Output requests return at most this many lines and bytes from the end of the log.
DEFAULT_TAIL_LINES = 200
MAX_TAIL_LINES = 2000
MAX_TAIL_BYTES = 256 * 1024
# Time a process group gets to exit after SIGTERM before it is sent SIGKILL.
TERMINATE_GRACE_SECONDS = 5.0
# How often the supervisor checks for the deadline and pending cancellation.
_POLL_SECONDS = 0.2
# The newest job records returned when no job ID is given.
LIST_LIMIT = 20
# Finished research job records and logs kept on disk. Older ones are pruned when a new job
# starts, so logs of up to 20 MiB each cannot accumulate forever. Scripts' own outputs in
# research_scripts/ are never touched.
MAX_KEPT_RESEARCH_JOBS = 100

RUNNING = 'running'
SUCCEEDED = 'succeeded'
FAILED = 'failed'
CANCELLED = 'cancelled'
TIMED_OUT = 'timed_out'
INTERRUPTED = 'interrupted'

JOB_ID_PATTERN = re.compile(r'[0-9a-f]{32}')

INTERRUPTED_MESSAGE = (
    'Jesse stopped or restarted while this job was running, so it is no longer tracked. '
    'After a normal shutdown the job was stopped; after a crash it may still be running.'
)


def _error(error_type: str, message: str, status_code: int) -> ProjectFileError:
    return ProjectFileError(error_type, message, status_code)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ---------------------------------------------------------------------------
# Job kinds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JobScope:
    """
    Where one kind of job keeps its record and output, and how many may run at once.

    Limits are callables so they are read when a job starts, which keeps them adjustable
    module constants of the module that defines the scope.
    """
    name: str
    label: str
    max_concurrent: Callable[[], int]
    max_log_bytes: Callable[[], int]
    record_path: Callable[[str], str]
    log_path: Callable[[str], str]
    write_record: Callable[[dict], None]
    id_hint: str


def _record_path(job_id: str) -> str:
    return os.path.join(JOBS_DIR, f'{job_id}.json')


def _log_path(job_id: str) -> str:
    return os.path.join(LOGS_DIR, f'{job_id}.txt')


def write_record_file(record: dict, path: str) -> None:
    """Replace a job record atomically so readers never see a half-written file."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp = f'{path}.{uuid4().hex}.tmp'
    try:
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=2)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _write_record(record: dict) -> None:
    write_record_file(record, _record_path(record['id']))


RESEARCH = JobScope(
    name='research',
    label='research job',
    max_concurrent=lambda: MAX_CONCURRENT_JOBS,
    max_log_bytes=lambda: MAX_LOG_BYTES,
    record_path=_record_path,
    log_path=_log_path,
    # Looked up at call time so the module-level writer can be replaced (e.g. in tests).
    write_record=lambda record: _write_record(record),
    id_hint='the 32-character ID returned by run_research_script',
)


def read_record_file(path: str, label: str, job_id: str) -> Optional[dict]:
    try:
        with open(path, encoding='utf-8') as f:
            record = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise _error('io_error', f'The record for {label} {job_id} could not be read.', 500)
    return record if isinstance(record, dict) else None


# ---------------------------------------------------------------------------
# Process supervision
# ---------------------------------------------------------------------------

class _Job:
    """A running job's process, its supervisor state, and the reason it is being stopped, if any."""

    def __init__(self, scope: JobScope, record: dict, process: subprocess.Popen):
        self.scope = scope
        self.record = record
        self.process = process
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.stop_reason: Optional[str] = None
        self.stop_sent_at = 0.0
        self.kill_sent = False
        self.output_truncated = False
        self.exit_code: Optional[int] = None
        # Set once a signal to the group fails because no member is left. After that the group
        # ID may be reused by an unrelated process, so it is never signalled again.
        self.group_gone = False

    @property
    def pgid(self) -> int:
        # start_new_session=True makes the process the leader of a group with its PID as ID.
        return self.process.pid

    def signal_group(self, sig: int) -> bool:
        """Signal every process in the job's group; False once none is left. Call with lock held."""
        if self.group_gone:
            return False
        try:
            os.killpg(self.pgid, sig)
            return True
        except (ProcessLookupError, PermissionError):
            # PermissionError: the ID now belongs to another user's group, so ours is gone.
            self.group_gone = True
            return False

    def request_stop(self, reason: str) -> bool:
        """
        Stop a job that is still running and remember why; False if it already exited.

        Once the script itself has exited, its result stands: the supervisor is only
        cleaning up leftover processes, so a late cancel must not relabel the job.
        """
        with self.lock:
            if self.stop_reason is not None or self.done.is_set() or self.exit_code is not None:
                return False
            self.stop_reason = reason
            self.stop_sent_at = time.monotonic()
            self.signal_group(signal.SIGTERM)
            return True

    def escalate_if_due(self) -> None:
        with self.lock:
            if self.stop_reason and not self.kill_sent and time.monotonic() - self.stop_sent_at >= TERMINATE_GRACE_SECONDS:
                self.kill_sent = True
                self.signal_group(signal.SIGKILL)

    def kill_now(self) -> None:
        with self.lock:
            self.signal_group(signal.SIGKILL)


_jobs: Dict[str, _Job] = {}
_jobs_lock = threading.Lock()


def _pump_output(job: _Job, log_file, max_bytes: int) -> None:
    """
    Copy combined stdout/stderr into the log, discarding output beyond max_bytes.

    The pipe is drained until it closes even when output is discarded or the log cannot be
    written (for example a full disk): a script blocked on a full pipe would otherwise hang
    until its deadline.
    """
    stream = job.process.stdout
    assert stream is not None
    written = 0
    fd = stream.fileno()
    with log_file:
        while True:
            try:
                chunk = os.read(fd, 64 * 1024)
            except OSError:
                break
            if not chunk:
                break
            if written >= max_bytes:
                continue  # Keep draining so the script never blocks on a full pipe.
            room = max_bytes - written
            try:
                log_file.write(chunk[:room])
                written += min(len(chunk), room)
                if written >= max_bytes:
                    log_file.write(
                        f'\n[Jesse: output limit of {max_bytes} bytes reached; further output was discarded]\n'.encode('utf-8')
                    )
                log_file.flush()
            except OSError:
                written = max_bytes  # Discard the rest, but keep draining.
            if written >= max_bytes:
                job.output_truncated = True
    stream.close()


def _cleanup_group(job: _Job) -> None:
    """
    Stop processes the job left running in its group after its main process exited.

    The main process has already been reaped here, so the group lives only as long as a
    leftover member does; once the last one exits, its ID is free for the kernel to reuse.
    Signalling stops at the first failure (`group_gone`), which limits the exposure to the
    moment between the last member exiting and the next signal (at most one poll interval).
    In that window a signal could reach an unrelated group only if the kernel had already
    handed this ID to a new process that made itself a group leader. That is unlikely with
    sequential PID allocation, but not impossible: Python offers no portable way (no
    `waitid(WNOWAIT)` on macOS) to hold the ID reserved.
    """
    with job.lock:
        if not job.signal_group(signal.SIGTERM):
            return
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while time.monotonic() < deadline:
        with job.lock:
            if not job.signal_group(0):
                return
        time.sleep(_POLL_SECONDS)
    job.kill_now()


def _supervise(job: _Job, deadline: float, pump: threading.Thread) -> None:
    """Enforce the deadline, escalate stops, then clean up the group and finalize the record."""
    persisted = False
    try:
        while True:
            try:
                exit_code = job.process.wait(timeout=_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    job.request_stop(TIMED_OUT)
                job.escalate_if_due()
        with job.lock:
            job.exit_code = exit_code
        _cleanup_group(job)
        # The pipe closes once every process holding it has exited. A process that escaped
        # the group (by starting its own session) can keep it open, so do not wait forever.
        pump.join(timeout=TERMINATE_GRACE_SECONDS)

        with job.lock:
            # Holding the lock while finishing means a late cancel cannot relabel the result.
            record = dict(job.record)
            if job.stop_reason is not None:
                record['status'] = job.stop_reason
            else:
                record['status'] = SUCCEEDED if exit_code == 0 else FAILED
            record['exit_code'] = exit_code
            record['finished_at'] = now_iso()
            record['output_truncated'] = job.output_truncated
            job.record = record
        # Persist before signalling completion, so shutdown and cancel callers that wait on
        # `done` return only once the final record is on disk.
        try:
            job.scope.write_record(record)
            persisted = True
        except OSError:
            pass  # The job stays in memory, so status requests answer until Jesse restarts.
        job.done.set()
    finally:
        with job.lock:
            if not job.done.is_set():
                # Supervision itself failed; never leave the job looking like it still runs.
                job.record = {**job.record, 'status': FAILED, 'finished_at': now_iso(),
                              'message': 'Jesse lost track of this job; check its output.'}
                job.done.set()
        if persisted:
            with _jobs_lock:
                if _jobs.get(job.record['id']) is job:
                    del _jobs[job.record['id']]


def _deadline(timeout_minutes: int) -> float:
    """Monotonic time at which a job started now is stopped as timed out."""
    return time.monotonic() + timeout_minutes * 60


def _running_jobs(scope: Optional[JobScope] = None) -> List[_Job]:
    """Jobs of `scope` (every scope when None) that have not finished. Call with _jobs_lock held."""
    return [job for job in _jobs.values() if not job.done.is_set() and (scope is None or job.scope is scope)]


def running_job_ids(scope: JobScope) -> set:
    with _jobs_lock:
        return {job.record['id'] for job in _running_jobs(scope)}


def validate_timeout(timeout_minutes: object, maximum: int) -> int:
    if isinstance(timeout_minutes, bool) or not isinstance(timeout_minutes, int) or not 1 <= timeout_minutes <= maximum:
        raise _error('invalid_request', f'timeout_minutes must be between 1 and {maximum}.', 400)
    return timeout_minutes


def launch(
    scope: JobScope,
    job_id: str,
    argv: List[str],
    cwd: str,
    record_fields: dict,
    timeout_minutes: int,
    env_overrides: Optional[Dict[str, str]] = None,
) -> dict:
    """
    Start `argv` without a shell in a new process group and return its record immediately.

    Refuses with `too_many_jobs` when the scope's concurrency limit is reached. The record is
    written to the scope's record path now and again when the job finishes.
    """
    with _jobs_lock:
        running = _running_jobs(scope)
        limit = scope.max_concurrent()
        if len(running) >= limit:
            raise _error(
                'too_many_jobs',
                f'{len(running)} {scope.label}s are already running (limit {limit}). '
                'Wait for one to finish or cancel it first.',
                429,
            )

        log_path = scope.log_path(job_id)
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            log_file = open(log_path, 'xb')
        except OSError as exc:
            raise _error('io_error', f'Could not create the job log: {exc.strerror or exc}.', 500)
        env = dict(os.environ)
        # Unbuffered output makes progress visible in the log while the job runs.
        env['PYTHONUNBUFFERED'] = '1'
        env.update(env_overrides or {})
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=True,
            )
        except OSError as exc:
            log_file.close()
            os.unlink(log_path)
            raise _error('start_failed', f'Could not start the {scope.label}: {exc.strerror or exc}.', 500)

        record = {
            'id': job_id,
            **record_fields,
            'status': RUNNING,
            'pid': process.pid,
            'exit_code': None,
            'started_at': now_iso(),
            'finished_at': None,
            'timeout_minutes': timeout_minutes,
            'output_truncated': False,
        }
        job = _Job(scope, record, process)
        _jobs[job_id] = job
        try:
            scope.write_record(record)
        except OSError:
            pass  # Tracked in memory; the record is written again when the job finishes.

        pump = threading.Thread(
            target=_pump_output, args=(job, log_file, scope.max_log_bytes()),
            name=f'{scope.name}-log-{job_id}', daemon=True,
        )
        pump.start()
        deadline = _deadline(timeout_minutes)
        threading.Thread(
            target=_supervise, args=(job, deadline, pump), name=f'{scope.name}-job-{job_id}', daemon=True
        ).start()
    return dict(record)


def check_job_id(job_id: object, scope: JobScope) -> str:
    if not isinstance(job_id, str) or not JOB_ID_PATTERN.fullmatch(job_id):
        raise _error('invalid_request', f'job_id must be {scope.id_hint}.', 400)
    return job_id


def get_scoped_job(job_id: str, scope: JobScope) -> dict:
    """Return a job's record; a record marked running with no live supervisor becomes interrupted."""
    check_job_id(job_id, scope)
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None and job.scope is scope:
            return dict(job.record)
    record = read_record_file(scope.record_path(job_id), scope.label, job_id)
    if record is None:
        raise _error('not_found', f'{scope.label.capitalize()} {job_id} does not exist.', 404)
    if record.get('status') == RUNNING:
        record['status'] = INTERRUPTED
        record['finished_at'] = record.get('finished_at') or now_iso()
        record['message'] = INTERRUPTED_MESSAGE
        try:
            scope.write_record(record)
        except OSError:
            pass
    return record


def read_scoped_output(job_id: str, tail_lines: int, scope: JobScope) -> dict:
    """Return the last `tail_lines` lines of a job's combined output, capped at MAX_TAIL_BYTES."""
    if isinstance(tail_lines, bool) or not isinstance(tail_lines, int) or not 1 <= tail_lines <= MAX_TAIL_LINES:
        raise _error('invalid_request', f'tail_lines must be between 1 and {MAX_TAIL_LINES}.', 400)
    record = get_scoped_job(job_id, scope)
    try:
        with open(scope.log_path(job_id), 'rb') as f:
            size = os.fstat(f.fileno()).st_size
            start = max(0, size - MAX_TAIL_BYTES)
            f.seek(start)
            data = f.read(MAX_TAIL_BYTES)
    except FileNotFoundError:
        size, start, data = 0, 0, b''
    text = data.decode('utf-8', errors='replace')
    lines = text.splitlines(keepends=True)
    if start > 0 and lines:
        lines = lines[1:]  # The first line may begin mid-line or mid-character.
    omitted = start > 0 or len(lines) > tail_lines
    lines = lines[-tail_lines:]
    return {
        'job_id': job_id,
        'job_status': record.get('status'),
        'output': ''.join(lines),
        'lines_returned': len(lines),
        'output_size_bytes': size,
        'earlier_output_omitted': omitted,
        'output_truncated': bool(record.get('output_truncated')),
    }


def cancel_scoped_job(job_id: str, scope: JobScope) -> dict:
    """Stop a running job's whole process group, waiting briefly for it to finish."""
    check_job_id(job_id, scope)
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None or job.scope is not scope:
        record = get_scoped_job(job_id, scope)
        return {'job': record, 'cancel_requested': False, 'message': f'The job is not running (status: {record.get("status")}).'}
    requested = job.request_stop(CANCELLED)
    # SIGKILL follows TERMINATE_GRACE_SECONDS after SIGTERM, and leftover children get the same
    # grace, so this normally returns the final record rather than "running".
    finished = job.done.wait(timeout=TERMINATE_GRACE_SECONDS * 2 + 2)
    record = dict(job.record)
    if not finished:
        message = 'Cancellation was requested; the job is still stopping. Check its status again shortly.'
    elif record.get('status') == CANCELLED:
        message = 'The job was cancelled.'
    else:
        message = f'The job finished before it could be cancelled (status: {record.get("status")}).'
    return {'job': record, 'cancel_requested': requested, 'message': message}


def terminate_all_jobs() -> None:
    """Stop every running job of every scope; called when the Jesse API shuts down."""
    with _jobs_lock:
        jobs = _running_jobs()
    for job in jobs:
        job.request_stop(INTERRUPTED)
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    for job in jobs:
        job.done.wait(timeout=max(0.0, deadline - time.monotonic()))
    for job in jobs:
        if not job.done.is_set():
            job.kill_now()
            job.done.wait(timeout=1)


# ---------------------------------------------------------------------------
# Research scripts
# ---------------------------------------------------------------------------

def _validate_args(args: object) -> List[str]:
    if args is None:
        return []
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise _error('invalid_request', 'args must be a list of strings.', 400)
    if len(args) > MAX_ARGS:
        raise _error('invalid_request', f'At most {MAX_ARGS} arguments are allowed.', 400)
    for arg in args:
        if len(arg) > MAX_ARG_LENGTH or '\x00' in arg:
            raise _error('invalid_request', f'Each argument must be at most {MAX_ARG_LENGTH} characters without NUL.', 400)
    return list(args)


def _resolve_script(path: str) -> str:
    """Return the project-relative path of an existing .py file under research_scripts/."""
    parts = parse_path(path)
    if parts[0] != RESEARCH_SCRIPTS_ROOT or len(parts) < 2 or not parts[-1].endswith('.py'):
        raise _error('invalid_path', 'Only .py files inside research_scripts/ can be run.', 400)
    # Opens every component without following symlinks and requires a regular file. The
    # interpreter then opens the same relative path; swapping a component in between needs
    # local write access to the project, which already allows running arbitrary code.
    fd = open_regular_file(parts)
    os.close(fd)
    return display_path(parts)


def _prune_research_jobs() -> None:
    """Delete the records and logs of the oldest finished research jobs beyond MAX_KEPT_RESEARCH_JOBS."""
    try:
        names = os.listdir(JOBS_DIR)
    except OSError:
        return
    running = running_job_ids(RESEARCH)
    finished = []
    for name in names:
        job_id = name[:-5]
        if not name.endswith('.json') or not JOB_ID_PATTERN.fullmatch(job_id) or job_id in running:
            continue
        try:
            finished.append((os.stat(_record_path(job_id)).st_mtime, job_id))
        except OSError:
            continue
    finished.sort(reverse=True)
    for _mtime, job_id in finished[MAX_KEPT_RESEARCH_JOBS:]:
        for path in (_record_path(job_id), _log_path(job_id)):
            try:
                os.unlink(path)
            except OSError:
                pass


def start_job(path: str, args: Optional[list] = None, timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES) -> dict:
    """Start a research script in the background and return its job record immediately."""
    validate_timeout(timeout_minutes, MAX_TIMEOUT_MINUTES)
    arguments = _validate_args(args)
    script = _resolve_script(path)
    _prune_research_jobs()

    job_id = uuid4().hex
    project_root = os.getcwd()
    # The project root on PYTHONPATH lets scripts import `strategies.<Name>` from any sub-folder.
    python_path = os.pathsep.join(filter(None, [project_root, os.environ.get('PYTHONPATH')]))
    return launch(
        RESEARCH,
        job_id,
        [sys.executable, script, *arguments],
        project_root,
        {'script': script, 'args': arguments, 'log_path': _log_path(job_id).replace(os.sep, '/')},
        timeout_minutes,
        {'PYTHONPATH': python_path},
    )


def get_job(job_id: str) -> dict:
    return get_scoped_job(job_id, RESEARCH)


def list_jobs(limit: int = LIST_LIMIT) -> List[dict]:
    """Return the newest research job records first."""
    try:
        names = [name for name in os.listdir(JOBS_DIR) if name.endswith('.json')]
    except FileNotFoundError:
        names = []
    ids = {name[:-5] for name in names if JOB_ID_PATTERN.fullmatch(name[:-5])}
    ids.update(running_job_ids(RESEARCH))
    records = []
    for job_id in ids:
        try:
            records.append(get_job(job_id))
        except ProjectFileError:
            continue
    records.sort(key=lambda record: record.get('started_at') or '', reverse=True)
    return records[:limit]


def read_output(job_id: str, tail_lines: int = DEFAULT_TAIL_LINES) -> dict:
    return read_scoped_output(job_id, tail_lines, RESEARCH)


def cancel_job(job_id: str) -> dict:
    return cancel_scoped_job(job_id, RESEARCH)
