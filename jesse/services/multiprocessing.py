from typing import List
from multiprocessing import Process


class ProcessManager:
    def __init__(self):
        self.workers: List[Process] = []
        self.pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}

    def reset(self):
        self.workers = []
        self.pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}

    def cleanup(self):
        self.workers = [w for w in self.workers if w.is_alive()]

    def add_task(self, function, client_id, *args):
        w = Process(target=function, args=args)
        self.workers.append(w)
        w.start()
        self.pid_to_client_id_map[w.pid] = client_id
        self.client_id_to_pid_to_map[client_id] = w.pid

    def get_client_id(self, pid):
        client_id: str = self.pid_to_client_id_map[pid]
        # return after "-" because we add them before sending it to multiprocessing
        return client_id[client_id.index('-') + len('-'):]

    def get_pid(self, client_id):
        return self.client_id_to_pid_to_map[client_id]

    def cancel_process(self, client_id):
        pid = self.get_pid(client_id)
        for i, w in enumerate(self.workers):
            if w.is_alive() and w.pid == pid:
                del self.client_id_to_pid_to_map[client_id]
                del self.pid_to_client_id_map[w.pid]
                w.terminate()
                w.join()
                w.close()
                del self.workers[i]
                return

    def flush(self):
        for w in self.workers:
            w.terminate()
            w.join()
            w.close()
        process_manager.reset()


process_manager = ProcessManager()
