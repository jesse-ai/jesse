import threading
import time
from typing import List
import multiprocessing as mp
import traceback
from jesse.services.redis import sync_publish, sync_redis
from jesse.services.failure import terminate_session
import jesse.helpers as jh
from jesse.services.env import ENV_VALUES

# set multiprocessing process type to spawn
mp.set_start_method('spawn', force=True)


def _terminal_debug(message: str) -> None:
    try:
        jh.terminal_debug(message)
    except Exception:
        pass


class Process(mp.Process):
    def __init__(self, *args, **kwargs):
        mp.Process.__init__(self, *args, **kwargs)

    def run(self):
        try:
            mp.Process.run(self)
        except Exception as e:
            if type(e).__name__ == 'Termination':
                sync_publish('termination', {})
                jh.terminate_app()
            else:
                sync_publish(
                    'exception',
                    {
                        'error': f'{type(e).__name__}: {e}',
                        'traceback': str(traceback.format_exc()),
                    },
                )

                print('Unhandled exception in the process:')
                print(traceback.format_exc())

                terminate_session()


class ProcessManager:
    def __init__(self):
        self._workers: List[Process] = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}
        self._pending_worker_removals: set[str] = set()
        self._workers_lock = threading.Lock()
        self._shutting_down = False
        try:
            port = ENV_VALUES.get('APP_PORT', '9000')
        except:
            port = '9000'
            
        self._active_workers_key = f"{port}|active-processes"
        self._cleanup_thread = threading.Thread(target=self._cleanup_finished_workers, daemon=True)
        self._cleanup_thread.start()

    def _reset(self):
        client_ids = {
            jh.string_after_character(prefixed_client_id, '|')
            for prefixed_client_id in self.client_id_to_pid_to_map
        }
        self._pending_worker_removals.update(client_ids)
        self._workers = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}
        # clear all process status
        try:
            sync_redis.delete(self._active_workers_key)
        except Exception as e:
            _terminal_debug(
                f'Error clearing active workers from coordinator; cleanup will retry: {type(e).__name__}: {e}'
            )
        else:
            self._pending_worker_removals.clear()

    @staticmethod
    def _prefixed_pid(pid):
        return f"{ENV_VALUES['APP_PORT']}|{pid}"

    @staticmethod
    def _prefixed_client_id(client_id):
        return f"{ENV_VALUES['APP_PORT']}|{client_id}"

    def _add_process(self, client_id):
        sync_redis.sadd(self._active_workers_key, client_id)

    def add_task(self, function, *args):
        client_id = args[0]
        with self._workers_lock:
            if self._shutting_down:
                raise RuntimeError('Jesse is shutting down; cannot launch another session')
            w = Process(target=function, args=args)
            self._workers.append(w)

            # The worker may check its active marker immediately, so publish it
            # before the child can begin executing. This also makes cancellation
            # a reliable cooperative signal instead of a startup race. Publishing
            # can fail too (coordinator unreachable); then the never-started worker must
            # not stay in _workers, where cleanup could never join or remove it.
            self._pending_worker_removals.discard(client_id)
            try:
                self._add_process(client_id)
                w.start()
            except Exception:
                self._workers.remove(w)
                self._remove_active_worker(client_id)
                raise

            prefixed_pid = self._prefixed_pid(w.pid)
            prefixed_client_id = self._prefixed_client_id(client_id)
            self._pid_to_client_id_map[prefixed_pid] = prefixed_client_id
            self.client_id_to_pid_to_map[prefixed_client_id] = prefixed_pid

    def get_client_id(self, pid):
        try:
            client_id: str = self._pid_to_client_id_map[self._prefixed_pid(pid)]
        except KeyError:
            return None
        return jh.string_after_character(client_id, '|')

    def get_pid(self, client_id):
        return self.client_id_to_pid_to_map[self._prefixed_client_id(client_id)]

    def cancel_process(self, client_id):
        sync_redis.srem(self._active_workers_key, client_id)

    def shutdown(self) -> None:
        """Allow cooperative session cleanup before bounded forced process removal."""
        with self._workers_lock:
            # The same lock guards launches, so none can escape the shutdown snapshot.
            self._shutting_down = True
            workers = list(self._workers)
            client_ids = list(self.client_id_to_pid_to_map)
            for prefixed in client_ids:
                try:
                    self.cancel_process(jh.string_after_character(prefixed, '|'))
                except Exception:
                    # Private-service failure is also observed by managed workers;
                    # a broken coordinator must not prevent final process cleanup.
                    pass
        # Live sessions poll once per second and may need time for their configured
        # termination work. Bound the whole group, rather than ten seconds per worker.
        deadline = time.monotonic() + 10
        for worker in workers:
            try:
                worker.join(timeout=max(0, deadline - time.monotonic()))
            except Exception as exc:
                # Cleanup can close _popen between join's checks; still force-reap the rest.
                _terminal_debug(f'Worker join during shutdown: {type(exc).__name__}: {exc}')
        self.flush()

    def flush(self):
        with self._workers_lock:
            for w in self._workers:
                try:
                    # Try terminate first
                    w.terminate()
                    # Give it a moment to terminate gracefully
                    w.join(timeout=3)
                    
                    # If still alive, wait a brief moment then force kill
                    if w.is_alive():
                        time.sleep(0.5)  # Give terminate a chance to complete
                        # multiprocessing uses TerminateProcess on Windows and SIGKILL on Unix.
                        w.kill()
                        w.join(timeout=3)

                    w.close()
                except Exception as e:
                    jh.debug(f"Error while terminating process: {str(e)}")

            self._reset()

    def _remove_active_worker(self, client_id: str) -> bool:
        """Remove a finished worker's coordinator marker, or retain it for retry."""
        was_pending = client_id in self._pending_worker_removals
        try:
            sync_redis.srem(self._active_workers_key, client_id)
        except Exception as e:
            self._pending_worker_removals.add(client_id)
            if not was_pending:
                _terminal_debug(
                    f'Error removing finished worker {client_id} from coordinator; cleanup will retry: '
                    f'{type(e).__name__}: {e}'
                )
            return False
        else:
            self._pending_worker_removals.discard(client_id)
            return True

    def _retry_pending_worker_removals(self) -> None:
        """Retry coordinator cleanup without removing markers owned by newer workers."""
        for client_id in tuple(self._pending_worker_removals):
            if self._prefixed_client_id(client_id) in self.client_id_to_pid_to_map:
                self._pending_worker_removals.discard(client_id)
                continue
            if self._remove_active_worker(client_id):
                _terminal_debug(f"Removed deferred worker {client_id} from active workers")
            else:
                # One timeout is enough to treat coordinator as unavailable for this cycle. Stopping here
                # bounds how long cleanup holds the worker lock while coordinator remains unreachable.
                break

    def _cleanup_finished_workers(self):
        from jesse.services import session_liveness
        last_renewal = 0.0
        while True:
            exited = []
            live_client_ids = []
            try:
                with self._workers_lock:
                    self._retry_pending_worker_removals()
                    for w in self._workers[:]:  # Create a copy of the list to avoid modification during iteration
                        if not w.is_alive():
                            try:
                                prefixed_pid = self._prefixed_pid(w.pid)
                                prefixed_client_id = self._pid_to_client_id_map.get(prefixed_pid)

                                w.join(timeout=1)
                                exit_code = w.exitcode
                                worker_pid = w.pid
                                client_id = (
                                    jh.string_after_character(prefixed_client_id, '|')
                                    if prefixed_client_id
                                    else 'unknown'
                                )
                                _terminal_debug(
                                    f'Worker {client_id} (PID {worker_pid}) exited with code {exit_code}'
                                )
                                w.close()
                                self._workers.remove(w)
                                self._pid_to_client_id_map.pop(prefixed_pid, None)

                                if (
                                    prefixed_client_id
                                    and self.client_id_to_pid_to_map.get(prefixed_client_id) == prefixed_pid
                                ):
                                    self.client_id_to_pid_to_map.pop(prefixed_client_id, None)
                                    # Only the session's latest worker decides its fate; a rerun
                                    # may already have started a newer one under the same id.
                                    exited.append((client_id, exit_code))
                                    if self._remove_active_worker(client_id):
                                        _terminal_debug(f"Cleaned up finished worker {client_id}")
                            except Exception as e:
                                _terminal_debug(f"Error during worker cleanup: {type(e).__name__}: {e}")
                    live_client_ids = [
                        jh.string_after_character(client_id, '|')
                        for client_id, pid in self.client_id_to_pid_to_map.items()
                    ]
            except Exception as e:
                _terminal_debug(f"Error in cleanup thread: {type(e).__name__}: {e}")
            # Outside the lock: the database may be slow, and starting workers must not wait on it.
            for client_id, exit_code in exited:
                self._reconcile_exited_session(client_id, exit_code)
            if live_client_ids and time.monotonic() - last_renewal >= session_liveness.HEARTBEAT_INTERVAL_SECONDS:
                last_renewal = time.monotonic()
                try:
                    session_liveness.renew_leases(live_client_ids)
                except Exception as e:
                    _terminal_debug(f'Error renewing session leases: {type(e).__name__}: {e}')
            time.sleep(5)

    @staticmethod
    def _reconcile_exited_session(client_id: str, exit_code) -> None:
        """Stop a research session that still says running after its worker exited."""
        try:
            from jesse.services.session_liveness import reconcile_exited_worker
            stopped = reconcile_exited_worker(client_id, exit_code)
        except Exception as e:
            _terminal_debug(f'Error reconciling session {client_id} after its worker exited: {type(e).__name__}: {e}')
            return
        for kind in stopped:
            _terminal_debug(f'Marked {kind} session {client_id} stopped: its worker exited with code {exit_code}')

    @property
    def active_workers(self) -> set:
        """
        Returns the set of all the processes client_id as a list of strings
        """
        return {client_id.decode('utf-8') for client_id in sync_redis.smembers(self._active_workers_key)}


process_manager = ProcessManager()
