from typing import List
import multiprocessing as mp
import traceback
from jesse.services.redis import sync_publish, sync_redis
from jesse.services.failure import terminate_session
import jesse.helpers as jh
from datetime import timedelta
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

    def _reset(self):
        self._workers = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}

    @staticmethod
    def _prefixed_pid(pid):
        return f"{ENV_VALUES['APP_PORT']}|{pid}"

    @staticmethod
    def _prefixed_client_id(client_id):
        return f"{ENV_VALUES['APP_PORT']}|{client_id}"

    def _set_process_status(self, pid, status):
        seconds = 3600 * 24 * 365  # one year
        key = f"{ENV_VALUES['APP_PORT']}|process-status:{pid}"
        value = f'status:{status}'
        sync_redis.setex(key, timedelta(seconds=seconds), value)

    def add_task(self, function, client_id, *args):
        w = Process(target=function, args=args)
        self._workers.append(w)
        w.start()

        self._pid_to_client_id_map[self._prefixed_pid(w.pid)] = self._prefixed_client_id(client_id)
        self.client_id_to_pid_to_map[self._prefixed_client_id(client_id)] = self._prefixed_pid(w.pid)
        self._set_process_status(w.pid, 'started')

    def get_client_id(self, pid):
        client_id: str = self._pid_to_client_id_map[self._prefixed_pid(pid)]
        # return after "-" because we add them before sending it to multiprocessing
        return client_id[client_id.index('-') + len('-'):]

    def get_pid(self, client_id):
        return self.client_id_to_pid_to_map[self._prefixed_client_id(client_id)]

    def cancel_process(self, client_id):
        pid = self.get_pid(client_id)
        pid = jh.string_after_character(pid, '|')
        self._set_process_status(pid, 'stopping')

    def flush(self):
        for w in self._workers:
            w.terminate()
            w.join()
            w.close()
        process_manager._reset()


process_manager = ProcessManager()
