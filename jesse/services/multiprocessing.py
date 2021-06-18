from typing import List
from multiprocessing import Process


class ProcessManager:
    def __init__(self):
        self.workers: List[Process] = []

    def reset(self):
        self.workers = []

    def add_task(self, function, *args):
        w = Process(target=function, args=args)
        self.workers.append(w)
        w.start()

    def flush(self):
        for w in self.workers:
            print(w.name, w.pid)
            w.terminate()
            w.join()
            w.close()
        process_manager.reset()


process_manager = ProcessManager()
