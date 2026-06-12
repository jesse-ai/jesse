import numpy as np

from jesse.helpers import np_shift


class DynamicNumpyArray:
    """
    Dynamic Numpy Array

    A data structure containing a numpy array which expands its memory
    allocation every N number. Hence, it's both fast and dynamic.
    """

    def __init__(self, shape: tuple, drop_at: int = None):
        self.index = -1
        self.array = np.zeros(shape)
        self.bucket_size = shape[0]
        self.shape = shape
        self.drop_at = drop_at

    def __str__(self) -> str:
        return str(self.array[:self.index + 1])

    def __len__(self) -> int:
        return self.index + 1

    def __getitem__(self, i):
        # hot path (runs per simulated minute): hoist the attribute read and
        # use `i += index + 1` instead of the old abs()-based negative-index
        # math — identical arithmetic for the negative values it applies to
        index = self.index
        if isinstance(i, slice):
            start = 0 if i.start is None else i.start
            stop = index + 1 if i.stop is None else i.stop

            if stop < 0:
                stop += index + 1
            if stop > index + 1:
                stop = index + 1
            return self.array[start:stop]
        else:
            if i < 0:
                i += index + 1

            # validation
            if index == -1 or i > index or i < 0:
                raise IndexError(f'list assignment index out of range. self.index={index}, i={i}')

            return self.array[i]

    def __setitem__(self, i, item) -> None:
        if isinstance(i, slice):
            start = i.start
            stop = i.stop
            step = i.step
            if start is not None and start < 0:
                start = (self.index + 1) - abs(start)
            if stop is None:
                stop = start + len(item)
            if stop < 0:
                stop = (self.index + 1) - abs(stop)
            self.array[slice(start, stop, step)] = item
            return

        if i < 0:
            i += self.index + 1

        # validation
        if i > self.index or i < 0:
            raise IndexError('list assignment index out of range')

        self.array[i] = item

    def append(self, item: np.ndarray) -> None:
        self.index += 1

        # Grow the buffer when full, doubling capacity (geometric growth) so
        # that total bytes copied across all appends is O(N) rather than the
        # O(N^2 / bucket_size) of linear-bucket growth via np.concatenate.
        if self.index >= len(self.array):
            new_size = max(len(self.array) * 2, max(self.bucket_size, 1))
            new_shape = (new_size,) + tuple(self.array.shape[1:])
            new_array = np.zeros(new_shape, dtype=self.array.dtype)
            if self.index > 0:
                new_array[:self.index] = self.array[:self.index]
            self.array = new_array

        # drop N% of the beginning values to free memory
        if (
            self.drop_at is not None
            and self.index != 0
            and (self.index + 1) % self.drop_at == 0
        ):
            shift_num = int(self.drop_at / 2)
            self.index -= shift_num
            self.array = np_shift(self.array, -shift_num)

        self.array[self.index] = item

    def get_last_item(self):
        # validation
        if self.index == -1:
            raise IndexError('list assignment index out of range. array is empty which means no past item exists')

        return self.array[self.index]

    def get_past_item(self, past_index) -> np.ndarray:
        # validation
        if self.index == -1:
            raise IndexError('list assignment index out of range. array is empty which means no past item exists')
        # validation
        if (self.index - past_index) < 0:
            raise IndexError(f'list assignment index out of range. Max allowed is self.index={self.index}, past_index={past_index}')

        return self.array[self.index - past_index]

    def flush(self) -> None:
        self.index = -1
        self.array = np.zeros(self.shape)
        self.bucket_size = self.shape[0]

    def append_multiple(self, items: np.ndarray) -> None:
        n_new = len(items)
        old_index = self.index
        self.index += n_new

        # Grow the buffer geometrically (double) when needed. Must accommodate
        # `self.index + 1` total elements; ensure we double-or-better to avoid
        # degrading to linear growth when many small batches are appended.
        if self.index + 1 > len(self.array):
            min_required = self.index + 1
            new_size = max(min_required, len(self.array) * 2, max(self.bucket_size, 1))
            new_shape = (new_size,) + tuple(self.array.shape[1:])
            new_array = np.zeros(new_shape, dtype=self.array.dtype)
            if old_index >= 0:
                new_array[:old_index + 1] = self.array[:old_index + 1]
            self.array = new_array

        # drop N% of the beginning values to free memory
        if (
            self.drop_at is not None
            and self.index != 0
            and (self.index + 1) % self.drop_at == 0
        ):
            shift_num = int(self.drop_at / 2)
            self.index -= shift_num
            self.array = np_shift(self.array, -shift_num)

        self.array[self.index - n_new + 1 : self.index + 1] = items

    def delete(self, index: int, axis=None) -> None:
        self.array = np.delete(self.array, index, axis=axis)
        self.index -= 1
        if self.array.shape[0] <= self.shape[0]:
            new_bucket = np.zeros(self.shape)
            self.array = np.concatenate((self.array, new_bucket), axis=0)



