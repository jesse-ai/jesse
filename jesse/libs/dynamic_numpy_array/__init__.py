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
        if isinstance(i, slice):
            start = 0 if i.start is None else i.start
            stop = self.index + 1 if i.stop is None else i.stop

            if stop < 0:
                stop = (self.index + 1) - abs(stop)
            stop = min(stop, self.index + 1)
            return self.array[start:stop]
        else:
            if i < 0:
                i = (self.index + 1) - abs(i)

            # validation
            if self.index == -1 or i > self.index or i < 0:
                raise IndexError('list assignment index out of range')

            return self.array[i]

    def __setitem__(self, i, item) -> None:
        if i < 0:
            i = (self.index + 1) - abs(i)

        # validation
        if i > self.index or i < 0:
            raise IndexError('list assignment index out of range')

        self.array[i] = item

    def append(self, item: np.ndarray) -> None:
        self.index += 1

        # expand if the arr is almost full
        if self.index != 0 and (self.index + 1) % self.bucket_size == 0:
            new_bucket = np.zeros(self.shape)
            self.array = np.concatenate((self.array, new_bucket), axis=0)

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
            raise IndexError('list assignment index out of range')

        return self.array[self.index]

    def get_past_item(self, past_index) -> np.ndarray:
        # validation
        if self.index == -1:
            raise IndexError('list assignment index out of range')
        # validation
        if (self.index - past_index) < 0:
            raise IndexError('list assignment index out of range')

        return self.array[self.index - past_index]

    def flush(self) -> None:
        self.index = -1
        self.array = np.zeros(self.shape)
        self.bucket_size = self.shape[0]
