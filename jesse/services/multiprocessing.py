from typing import List
from multiprocessing import Process


class ProcessManager:
    def __init__(self):
        self.workers: List[Process] = []
        self.map = {}

    def reset(self):
        self.workers = []
        self.map = {}

    def add_task(self, function, client_id, *args):
        w = Process(target=function, args=args)
        self.workers.append(w)
        w.start()
        self.map[w.pid] = client_id
        print(w.pid, w.name)

    def flush(self):
        for w in self.workers:
            print(w.name, w.pid)
            w.terminate()
            w.join()
            w.close()
        process_manager.reset()


process_manager = ProcessManager()
