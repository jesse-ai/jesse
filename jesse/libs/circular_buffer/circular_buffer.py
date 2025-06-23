class CircularBuffer:
    
    def __init__(self, size):
        if size is None or size < 0:
            raise ValueError("CircularBuffer size must be a positive integer")
        self._buffer = [None] * size
        self._max_size = size
        self._write_index = 0
        self._count = 0  # Number of valid elements in buffer

    def __len__(self):
        return self._count

    def __iter__(self):
        start = (self._write_index - self._count) % self._max_size
        for i in range(self._count):
            yield self._buffer[(start + i) % self._max_size]

    def __getitem__(self, idx):
        start = (self._write_index - self._count) % self._max_size
        if isinstance(idx, slice): # Slicing is slower and not recommended
            size = self._count
            start_idx, stop_idx, step = idx.indices(size)

            if step == 1:
                length = max(0, stop_idx - start_idx)
                return [self._buffer[(start + i) % self._max_size] for i in range(start_idx, start_idx + length)]
            else:
                return [self._buffer[(start + i) % self._max_size] for i in range(start_idx, stop_idx, step)]

        # Single index case
        if not -self._count <= idx < self._count:
            raise IndexError(f"Index {idx} out of range")
        if idx < 0:
            idx += self._count
        return self._buffer[(start + idx) % self._max_size]

    def append(self, value):
        self._buffer[self._write_index] = value
        self._write_index = (self._write_index + 1) % self._max_size
        if self._count < self._max_size:
            self._count += 1

    def clear(self):
        self._write_index = 0
        self._count = 0
        self._buffer = [None] * self._max_size

    @property
    def has_wrapped_around(self): # Went full circle?
        return self._write_index == 0 and self._count == self._max_size