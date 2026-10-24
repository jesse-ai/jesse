"""
A research runner: takes queued jobs from the shared database and runs them here (see
services/runner_queue.py for the whole picture).

It runs either inside `jesse run` (RUNNER_SLOTS in .env; a hub with RESEARCH_RUNNERS=true also
starts one to save runner files locally) or alone with `jesse runner` on a machine that only
provides compute. Threads:
- a listener holding its own database connection that LISTENs for queue, cancel and file
  notifications and wakes the loop (it reconnects after a network drop);
- the loop, which wakes on a notification or every POLL_SECONDS: it refreshes the runner's row,
  drops jobs it no longer holds, claims jobs into free slots, and on the hub saves runner files.
Jobs run through the process manager like local runs, so their leases, progress and crash
handling are the same; on_worker_exit (called by the process manager) completes them.
"""

import importlib.util
import json
import os
import select
import shutil
import socket
import threading
import time
from typing import Optional

import jesse.helpers as jh
from jesse.services import code_bundle, machine_stats, runner_queue, session_liveness
from jesse.services.env import ENV_VALUES

POLL_SECONDS = 10
SWEEP_SECONDS = 60
MAX_RETURNED_FILE_BYTES = 50 * 1024 * 1024
_ENDED = ('finished', 'stopped', 'cancelled', 'terminated')

_current: Optional['Runner'] = None


def current() -> Optional['Runner']:
    return _current


def _log(message: str) -> None:
    print(jh.color(f'[runner] {message}', 'cyan'), flush=True)


def _listen_connection():
    import psycopg2
    from jesse.services.db import postgres_schema

    connection = psycopg2.connect(
        dbname=ENV_VALUES['POSTGRES_NAME'], user=ENV_VALUES['POSTGRES_USERNAME'],
        password=ENV_VALUES['POSTGRES_PASSWORD'], host=ENV_VALUES['POSTGRES_HOST'],
        port=int(ENV_VALUES['POSTGRES_PORT']), sslmode=ENV_VALUES.get('POSTGRES_SSLMODE', 'disable'),
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
        options=f'-c search_path={postgres_schema()}',
    )
    connection.set_isolation_level(0)  # autocommit: notifications arrive outside transactions
    with connection.cursor() as cursor:
        for channel in (runner_queue.CHANNEL_JOBS, runner_queue.CHANNEL_CANCEL, runner_queue.CHANNEL_FILES):
            cursor.execute(f'LISTEN {channel}')
    return connection


class Runner:
    def __init__(self, name: str, slots: int, hub: bool, project_root: str = '.'):
        self.name = name
        self.slots = max(0, int(slots))
        self.hub = hub
        self.root = os.path.abspath(project_root)
        self.jobs: dict = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._cancel_requests: set = set()
        self._started_at = session_liveness.now_ms()
        self._last_sweep = 0.0
        self._threads = []

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        global _current
        _current = self
        session_liveness.set_machine_label(self.name)
        for target in (self._listen, self._loop):
            thread = threading.Thread(target=target, name=f'runner-{target.__name__}', daemon=True)
            thread.start()
            self._threads.append(thread)
        role = 'hub' if self.hub else 'runner'
        _log(f'{self.name} started as a {role} with {self.slots} slot(s), Jesse {runner_queue.jesse_version()}.')

    def stop(self) -> None:
        """Stop taking jobs and give running ones back to the queue for other runners."""
        global _current
        self._stopping.set()
        self._wake.set()
        with self._lock:
            jobs = dict(self.jobs)
            self.jobs.clear()
        from jesse.services.multiprocessing import process_manager
        for session_id, job in jobs.items():
            try:
                runner_queue.requeue(job, f'Runner {self.name} shut down; queued again.')
                process_manager.cancel_process(session_id, notify_runners=False)
            except Exception as e:
                jh.debug(f'Could not give job {session_id} back: {e}')
        try:
            self._heartbeat(busy=0, offline=True)
        except Exception:
            pass
        if _current is self:
            _current = None

    def wake(self) -> None:
        self._wake.set()

    # ------------------------------------------------------------------ threads
    def _listen(self) -> None:
        backoff = 1
        while not self._stopping.is_set():
            try:
                connection = _listen_connection()
            except Exception as e:
                jh.debug(f'Runner listener cannot connect: {e}')
                self._stopping.wait(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 1
            self._wake.set()  # catch up on anything queued while disconnected
            try:
                while not self._stopping.is_set():
                    if select.select([connection], [], [], 5) == ([], [], []):
                        continue
                    connection.poll()
                    while connection.notifies:
                        notification = connection.notifies.pop(0)
                        if notification.channel == runner_queue.CHANNEL_CANCEL:
                            self._cancel_requests.add(notification.payload)
                        self._wake.set()
            except Exception as e:
                jh.debug(f'Runner listener lost its connection: {e}')
            finally:
                try:
                    connection.close()
                except Exception:
                    pass

    def _loop(self) -> None:
        while not self._stopping.is_set():
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()
            if self._stopping.is_set():
                break
            try:
                self._tick()
            except Exception as e:
                jh.debug(f'Runner loop error: {type(e).__name__}: {e}')

    def _tick(self) -> None:
        self._heartbeat(busy=len(self.jobs))
        self._drop_lost_jobs()
        if self.hub:
            self._save_runner_files()
        if time.monotonic() - self._last_sweep > SWEEP_SECONDS:
            self._last_sweep = time.monotonic()
            runner_queue.sweep()
        while len(self.jobs) < self.slots and not self._stopping.is_set():
            job = runner_queue.claim_next(self.name)
            if job is None:
                break
            self._launch(job)
        self._heartbeat(busy=len(self.jobs))

    # ------------------------------------------------------------------ jobs
    def _heartbeat(self, busy: int, offline: bool = False) -> None:
        from jesse.models.RunnerJob import Runner as RunnerRow

        now = session_liveness.now_ms()
        stats = machine_stats.collect()
        values = {
            'host': socket.gethostname() or 'unknown-host', 'slots': self.slots, 'busy': busy,
            'cpu_cores': os.cpu_count() or 1, 'jesse_version': runner_queue.jesse_version(),
            'started_at': self._started_at, 'last_seen': 0 if offline else now,
            'cpu_percent': stats['cpu_percent'], 'load_1m': stats['load_1m'],
            'memory_total_bytes': stats['memory_total_bytes'], 'memory_used_bytes': stats['memory_used_bytes'],
        }
        updated = RunnerRow.update(**values).where(RunnerRow.name == self.name).execute()
        if not updated:
            RunnerRow.insert(name=self.name, **values).on_conflict_ignore().execute()

    def _launch(self, job: dict) -> None:
        from jesse.services.multiprocessing import process_manager
        from jesse.services.runner_worker import run_queued_job

        session_id = job['session_id']
        missing = [name for name in job['packages'] if importlib.util.find_spec(name) is None]
        if missing:
            reason = f"Runner {self.name} does not have the package(s) {', '.join(missing)}."
            _log(f'Gave back {job["kind"]} {session_id[:8]}: {reason}')
            runner_queue.release(job, self.name, reason)
            return
        job_dir = os.path.join(self.root, 'storage', 'runner', 'jobs', session_id)
        shutil.rmtree(job_dir, ignore_errors=True)
        try:
            os.makedirs(os.path.join(job_dir, 'storage'), exist_ok=True)
            code_bundle.materialize(job['code_manifest'], job_dir,
                                    os.path.join(self.root, 'storage', 'runner', 'cache'))
            self._link_env(job_dir)
            session_liveness.claim(job['kind'], session_id, mark_running=True, claim_id=job['claim_id'])
            job['job_dir'] = job_dir
            with self._lock:
                self.jobs[session_id] = job
            process_manager.add_task(run_queued_job, session_id, job['function'], json.dumps(job['arguments']),
                                     job_dir, job['claim_id'])
        except Exception as e:
            with self._lock:
                self.jobs.pop(session_id, None)
            reason = f'Runner {self.name} could not start the job: {type(e).__name__}: {e}'
            _log(reason)
            runner_queue.fail(job, reason)
            shutil.rmtree(job_dir, ignore_errors=True)
            return
        _log(f'Started {job["kind"]} {session_id[:8]} (attempt {job["attempt"]}).')

    def _link_env(self, job_dir: str) -> None:
        """
        Processes the job starts in its folder (Ray workers) load Jesse's settings from the .env
        there, so the folder gets this project's .env: a link, or a private copy where links fail.
        """
        source = os.path.join(self.root, '.env')
        target = os.path.join(job_dir, '.env')
        if not os.path.exists(source) or os.path.lexists(target):
            return
        try:
            os.symlink(source, target)
        except OSError:
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)

    def _drop_lost_jobs(self) -> None:
        """Stop workers whose job was cancelled or taken over by another runner."""
        from jesse.models.RunnerJob import RunnerJob
        from jesse.services.multiprocessing import process_manager

        with self._lock:
            jobs = dict(self.jobs)
        for session_id, job in jobs.items():
            row = RunnerJob.get_or_none(RunnerJob.id == job['id'])
            lost = row is None or row.claim_id != job['claim_id'] or row.status != 'running'
            if lost or session_id in self._cancel_requests:
                self._cancel_requests.discard(session_id)
                with self._lock:
                    self.jobs.pop(session_id, None)
                process_manager.cancel_process(session_id, notify_runners=False)
                _log(f'Stopped {job["kind"]} {session_id[:8]}: '
                     f'{"cancelled" if row is not None and row.status == "cancelled" else "no longer held here"}.')
                shutil.rmtree(job.get('job_dir', ''), ignore_errors=True)
        self._cancel_requests.clear()

    def on_worker_exit(self, client_id: str, exit_code) -> None:
        """Called by the process manager when a worker exits: complete the job and send its files."""
        with self._lock:
            job = self.jobs.pop(client_id, None)
        if job is None:
            return
        try:
            from jesse.services.session_status import lookup_session

            session = lookup_session(job['kind'], client_id)
            status = getattr(session, 'status', None)
            error = None if status in _ENDED else f'The worker exited with code {exit_code} and status {status}.'
            runner_queue.finish(job['id'], job['claim_id'], status, error)
            self._return_files(job)
            _log(f'Finished {job["kind"]} {client_id[:8]}: {status}.')
        except Exception as e:
            jh.debug(f'Runner could not complete job {client_id}: {e}')
        finally:
            shutil.rmtree(job.get('job_dir', ''), ignore_errors=True)
            self._wake.set()

    def _return_files(self, job: dict) -> None:
        """Send the files the run wrote (logs, charts, exports) to the hub through the database."""
        import uuid
        from jesse.models.RunnerJob import RunnerFile

        storage = os.path.join(job['job_dir'], 'storage')
        sent = 0
        for root, dirs, files in os.walk(storage):
            dirs[:] = [d for d in dirs if d not in ('temp', 'runner')]
            for name in files:
                path = os.path.join(root, name)
                if os.path.getsize(path) > MAX_RETURNED_FILE_BYTES:
                    continue
                relative = os.path.relpath(path, job['job_dir']).replace(os.sep, '/')
                with open(path, 'rb') as f:
                    RunnerFile.insert(id=str(uuid.uuid4()), session_id=job['session_id'], path=relative,
                                      content=f.read(), created_at=session_liveness.now_ms()).execute()
                sent += 1
        if job['kind'] == 'significance_test':
            self._relativize_chart_path(job)
        if sent:
            runner_queue.notify(runner_queue.CHANNEL_FILES, job['session_id'])

    @staticmethod
    def _relativize_chart_path(job: dict) -> None:
        from jesse.models.SignificanceTestSession import SignificanceTestSession

        row = SignificanceTestSession.get_or_none(SignificanceTestSession.id == job['session_id'])
        if row is not None and row.chart_path and row.chart_path.startswith(job['job_dir']):
            relative = os.path.relpath(row.chart_path, job['job_dir']).replace(os.sep, '/')
            SignificanceTestSession.update(chart_path=relative).where(
                SignificanceTestSession.id == job['session_id']).execute()

    def _save_runner_files(self) -> None:
        """On the hub: write the files runners sent into this project's storage, then drop them."""
        from jesse.models.RunnerJob import RunnerFile

        for row in RunnerFile.select().order_by(RunnerFile.created_at).limit(200):
            relative = os.path.normpath(row.path)
            if relative.startswith('storage' + os.sep) and '..' not in relative.split(os.sep):
                target = os.path.join(self.root, relative)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                temporary = f'{target}.part'
                with open(temporary, 'wb') as f:
                    f.write(bytes(row.content))
                os.replace(temporary, target)
            RunnerFile.delete().where(RunnerFile.id == row.id).execute()


def _slots_from_env(default: int) -> int:
    try:
        return max(0, int(ENV_VALUES.get('RUNNER_SLOTS', default)))
    except ValueError:
        return default


def start_in_server() -> Optional[Runner]:
    """Start a runner inside `jesse run` when this instance is a hub or offers runner slots."""
    hub = runner_queue.enabled()
    slots = _slots_from_env(1 if hub else 0)
    if not hub and slots == 0:
        return None
    runner = Runner(session_liveness.machine_label(), slots, hub)
    runner.start()
    return runner
