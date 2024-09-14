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
        self._active_workers_key = f"{ENV_VALUES['APP_PORT']}|active-processes"
        self._cleanup_thread = threading.Thread(target=self._cleanup_finished_workers, daemon=True)
        self._cleanup_thread.start()

    def _reset(self):
        self._workers = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}
        # clear all process status
        sync_redis.delete(self._active_workers_key)

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
        self._workers.append(w)
        w.start()

        self._pid_to_client_id_map[self._prefixed_pid(w.pid)] = self._prefixed_client_id(client_id)
        self.client_id_to_pid_to_map[self._prefixed_client_id(client_id)] = self._prefixed_pid(w.pid)
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
        for w in self._workers:
            w.terminate()
            w.join()
            w.close()
        self._reset()

    def _cleanup_finished_workers(self):
        while True:
            for w in self._workers:
                if not w.is_alive():
                    w.join()
                    w.close()
                    self._workers.remove(w)
            time.sleep(5)

    @property
    def active_workers(self) -> set:
        """
        Returns the set of all the processes client_id as a list of strings
        """
        return {client_id.decode('utf-8') for client_id in sync_redis.smembers(self._active_workers_key)}


process_manager = ProcessManager()
# flush all processes on startup to avoid any leftover processes
# process_manager.flush()
