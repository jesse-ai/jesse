class CircularBuffer:
    """
    A fixed-size circular (ring) buffer that overwrites the oldest data when full.
    Oldest data starts at index 0.

    Useful for managing streaming or time series data efficiently. Supports O(1)
    insertion, indexing, and lazy deletion, with O(n) slicing performance.

    This version of circular buffer assumes input of streaming temporal data.
    Therefore, there is no delete or pop method.

    Most obvious use case is for real-time forming OHLC data.
    """

    def __init__(self, size):
        """
        Initialize the buffer with a maximum size.

        Args:
            size (int): The total capacity of the buffer.
        
        Raises:
            ValueError: If size is None or less than or equal to 0.

        Time Complexity:
            O(n) — for allocating internal buffer of size `n`.
        """
        if size is None or size <= 0:
            raise ValueError("CircularBuffer size must be a positive integer")
        self._buffer = [None] * size
        self._max_size = size
        self._write_index = 0
        self._count = 0  # Number of valid elements in buffer
        self._wrap_len = 0

    def __len__(self):
        """
        Return the number of elements currently stored in the buffer.

        Returns:
            int: Number of valid elements.

        Time Complexity:
            O(1)
        """
        return self._count

    def __iter__(self):
        """
        Iterate over the buffer in the order elements were inserted.

        Yields:
            object: Elements from oldest to newest.

        Time Complexity:
            O(n) — where n is the number of valid elements.
        """
        start = (self._write_index - self._count) % self._max_size
        for i in range(self._count):
            yield self._buffer[(start + i) % self._max_size]

    def __getitem__(self, idx):
        """
        Retrieve item(s) from the buffer by index or slice, in insertion order.

        Args:
            idx (int or slice): Index (0 is the oldest) or a slice of indices.

        Returns:
            object or list: Element(s) at the specified index or slice.

        Raises:
            IndexError: If index is out of range.

        Time Complexity:
            O(1) for single index access.
            O(k) for slicing k elements.
        """
        start = (self._write_index - self._count) % self._max_size
        if isinstance(idx, slice):
            size = self._count
            start_idx, stop_idx, step = idx.indices(size)

            if step == 1:
                length = max(0, stop_idx - start_idx)
                return [self._buffer[(start + i) % self._max_size] for i in range(start_idx, start_idx + length)]
            else:
                return [self._buffer[(start + i) % self._max_size] for i in range(start_idx, stop_idx, step)]

        if not -self._count <= idx < self._count:
            raise IndexError(f"Index {idx} out of range")
        if idx < 0:
            idx += self._count
        return self._buffer[(start + idx) % self._max_size]

    def append(self, value):
        """
        Add a new item to the buffer, overwriting the oldest if full.

        Args:
            value (object): The value to add to the buffer.

        Time Complexity:
            O(1)
        """
        self._buffer[self._write_index] = value
        self._write_index = (self._write_index + 1) % self._max_size
        self._wrap_len += 1
        if self._wrap_len > self._max_size:
            self._wrap_len = 1
        if self._count < self._max_size:
            self._count += 1

    def clear(self):
        """
        Reset the buffer by marking all data as invalid (lazy deletion).

        Time Complexity:
            O(1) — for clearing storage.
        """
        self._write_index = 0
        self._count = 0
        self._wrap_len = 0

    @property
    def wrap_len(self):
        """
        Returns the number of items the head has written before it has done one full cycle.

        Returns:
            int: Number of written items before one full cycle.

        Time Complexity:
            O(1)
        """
        return self._wrap_len

    @property
    def size(self):
        """
        Returns initial size of the buffer.

        Returns:
            int: Initial size of the buffer.

        Time Complexity:
            O(1)
        """
        return self._max_size