from time import time
import numpy as np
from jesse.libs import DynamicNumpyArray


class Progressbar:
    def __init__(self, length: int, step=1):
        self.length = length
        self.index = 0
        self._time = time()
        self._execution_times = DynamicNumpyArray((100, 1), 100)
        self.step = step

    def update(self):
        self.index += self.step
        now = time()
        self._execution_times.append(np.array([now - self._time]))
        self._time = now

    @property
    def current(self):
        return round(self.index / self.length * 100, 1)

    @property
    def average_execution_time(self):
        return self._execution_times[:].mean()

    @property
    def remaining_index(self):
        return self.length - self.index

    @property
    def estimated_remaining_seconds(self):
        return self.average_execution_time * self.remaining_index / self.step

