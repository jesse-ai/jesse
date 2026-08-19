import threading
import time
from typing import List
import multiprocessing as mp
import traceback
from jesse.services.redis import sync_publish, sync_redis
from jesse.services.failure import terminate_session
import jesse.helpers as jh
from jesse.services.env import ENV_VALUES
import os
import signal

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
                f'Error clearing active workers from Redis; cleanup will retry: {type(e).__name__}: {e}'
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
        w = Process(target=function, args=args)
        with self._workers_lock:
            self._workers.append(w)
            w.start()

            prefixed_pid = self._prefixed_pid(w.pid)
            prefixed_client_id = self._prefixed_client_id(client_id)
            self._pid_to_client_id_map[prefixed_pid] = prefixed_client_id
            self.client_id_to_pid_to_map[prefixed_client_id] = prefixed_pid
            # A new worker owns this Redis marker now, so an older deferred
            # cleanup must never remove it after a reconnect.
            self._pending_worker_removals.discard(client_id)
            self._add_process(client_id)

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
                        os.kill(w.pid, signal.SIGKILL)

                    w.close()
                except Exception as e:
                    jh.debug(f"Error while terminating process: {str(e)}")

            self._reset()

    def _remove_active_worker(self, client_id: str) -> bool:
        """Remove a finished worker's Redis marker, or retain it for retry."""
        was_pending = client_id in self._pending_worker_removals
        try:
            sync_redis.srem(self._active_workers_key, client_id)
        except Exception as e:
            self._pending_worker_removals.add(client_id)
            if not was_pending:
                _terminal_debug(
                    f'Error removing finished worker {client_id} from Redis; cleanup will retry: '
                    f'{type(e).__name__}: {e}'
                )
            return False
        else:
            self._pending_worker_removals.discard(client_id)
            return True

    def _retry_pending_worker_removals(self) -> None:
        """Retry Redis cleanup without removing markers owned by newer workers."""
        for client_id in tuple(self._pending_worker_removals):
            if self._prefixed_client_id(client_id) in self.client_id_to_pid_to_map:
                self._pending_worker_removals.discard(client_id)
                continue
            if self._remove_active_worker(client_id):
                _terminal_debug(f"Removed deferred worker {client_id} from active workers")
            else:
                # One timeout is enough to treat Redis as unavailable for this cycle. Stopping here
                # bounds how long cleanup holds the worker lock while Redis remains unreachable.
                break

    def _cleanup_finished_workers(self):
        while True:
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
                                    if self._remove_active_worker(client_id):
                                        _terminal_debug(f"Cleaned up finished worker {client_id}")
                            except Exception as e:
                                _terminal_debug(f"Error during worker cleanup: {type(e).__name__}: {e}")
            except Exception as e:
                _terminal_debug(f"Error in cleanup thread: {type(e).__name__}: {e}")
            time.sleep(5)

    @property
    def active_workers(self) -> set:
        """
        Returns the set of all the processes client_id as a list of strings
        """
        return {client_id.decode('utf-8') for client_id in sync_redis.smembers(self._active_workers_key)}


process_manager = ProcessManager()
