from time import time
import numpy as np
from jesse.libs import DynamicNumpyArray


class Progressbar:
    def __init__(self, length: int, step=1):
        self.length = length
        self.index = 0

        # validation
        if self.length <= self.index:
            raise ValueError('length must be greater than 0')

        self._time = time()
        self._execution_times = DynamicNumpyArray((3, 1), 3)
        self.step = step
        self.is_finished = False

    def update(self, advance: int | None = None):
        """Count completed work, normalizing timing samples for unequal batch sizes."""
        advance = self.step if advance is None else advance
        if advance <= 0:
            raise ValueError('advance must be greater than 0')
        now = time()
        if not self.is_finished:
            # Sparse replay can cross several nominal batches in one iteration.
            # Count the actual work and clamp the final partial batch to length.
            processed = min(advance, self.length - self.index)
            self.index += processed
            if self.index >= self.length:
                self.is_finished = True
            # ETA averages durations per nominal batch, even when update sizes vary.
            self._execution_times.append(np.array([(now - self._time) * self.step / processed]))
        self._time = now

    @property
    def current(self):
        if self.is_finished:
            return 100
        return round(self.index / self.length * 100, 1)

    @property
    def average_execution_seconds(self):
        return self._execution_times[:].mean()

    @property
    def remaining_index(self):
        if self.is_finished:
            return 0
        return self.length - self.index

    @property
    def estimated_remaining_seconds(self):
        if self.is_finished:
            return 0
        return self.average_execution_seconds * self.remaining_index / self.step

    def finish(self):
        self.is_finished = True
