from typing import List
import multiprocessing as mp
import traceback
from jesse.services.redis import sync_publish


class Process(mp.Process):
    def __init__(self, *args, **kwargs):
        mp.Process.__init__(self, *args, **kwargs)

    def run(self):
        try:
            mp.Process.run(self)
        except Exception as e:
            sync_publish('exception', {
                'error': str(e),
                'traceback': str(traceback.format_exc())
            })
            print('\n')
            # print(e)
            print(traceback.format_exc())
            print('\n')


class ProcessManager:
    def __init__(self):
        self._workers: List[Process] = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}

    def _reset(self):
        self._workers = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}

    def add_task(self, function, client_id, *args):
        w = Process(target=function, args=args)
        self._workers.append(w)
        w.start()
        self._pid_to_client_id_map[w.pid] = client_id
        self.client_id_to_pid_to_map[client_id] = w.pid

    def get_client_id(self, pid):
        client_id: str = self._pid_to_client_id_map[pid]
        # return after "-" because we add them before sending it to multiprocessing
        return client_id[client_id.index('-') + len('-'):]

    def get_pid(self, client_id):
        return self.client_id_to_pid_to_map[client_id]

    def cancel_process(self, client_id):
        pid = self.get_pid(client_id)
        for i, w in enumerate(self._workers):
            if w.is_alive() and w.pid == pid:
                del self.client_id_to_pid_to_map[client_id]
                del self._pid_to_client_id_map[w.pid]
                w.terminate()
                w.join()
                w.close()
                del self._workers[i]
                return

    def flush(self):
        for w in self._workers:
            w.terminate()
            w.join()
            w.close()
        process_manager._reset()


process_manager = ProcessManager()
