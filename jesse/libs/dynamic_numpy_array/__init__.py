import numpy as np

from jesse.helpers import np_shift


class DynamicNumpyArray:
    """
    Dynamic Numpy Array

    A data structure containing a numpy array which expands its memory
    allocation every N number. Hence, it's both fast and dynamic.
    """

    def __init__(self, shape: tuple, drop_at: int = None):
        self._state = (np.zeros(shape), -1)
        self.bucket_size = shape[0]
        self.shape = shape
        self.drop_at = drop_at

    @property
    def array(self) -> np.ndarray:
        return self._state[0]

    @array.setter
    def array(self, value: np.ndarray) -> None:
        self._state = (value, self._state[1])

    @property
    def index(self) -> int:
        return self._state[1]

    @index.setter
    def index(self, value: int) -> None:
        self._state = (self._state[0], value)

    def snapshot(self) -> tuple:
        return self._state

    def __str__(self) -> str:
        array, index = self._state
        return str(array[:index + 1])

    def __len__(self) -> int:
        return self._state[1] + 1

    def __getitem__(self, i):
        # hot path (runs per simulated minute): hoist the state read and use
        # `i += index + 1` instead of the old abs()-based negative-index math.
        array, index = self._state
        if isinstance(i, slice):
            start = 0 if i.start is None else i.start
            stop = index + 1 if i.stop is None else i.stop

            if stop < 0:
                stop += index + 1
            if stop > index + 1:
                stop = index + 1
            return array[start:stop]
        else:
            if i < 0:
                i += index + 1

            # validation
            if index == -1 or i > index or i < 0:
                raise IndexError(f'list assignment index out of range. self.index={index}, i={i}')

            return array[i]

    def __setitem__(self, i, item) -> None:
        array, index = self._state
        if isinstance(i, slice):
            start = i.start
            stop = i.stop
            step = i.step
            if start is not None and start < 0:
                start = (index + 1) - abs(start)
            if stop is None:
                stop = start + len(item)
            if stop < 0:
                stop = (index + 1) - abs(stop)
            array[slice(start, stop, step)] = item
            return

        if i < 0:
            i += index + 1

        # validation
        if i > index or i < 0:
            raise IndexError('list assignment index out of range')

        array[i] = item

    def append(self, item: np.ndarray) -> None:
        array, current_index = self._state
        new_index = current_index + 1

        # Prepare capacity and the new row before atomically publishing the
        # complete state used by live readers on another thread.
        if new_index >= len(array):
            new_size = max(len(array) * 2, max(self.bucket_size, 1))
            new_shape = (new_size,) + tuple(array.shape[1:])
            new_array = np.zeros(new_shape, dtype=array.dtype)
            if current_index >= 0:
                new_array[:current_index + 1] = array[:current_index + 1]
            array = new_array

        # drop N% of the beginning values to free memory
        if (
            self.drop_at is not None
            and new_index != 0
            and (new_index + 1) % self.drop_at == 0
        ):
            shift_num = int(self.drop_at / 2)
            new_index -= shift_num
            array = np_shift(array, -shift_num)

        array[new_index] = item
        self._state = (array, new_index)

    def get_last_item(self):
        array, index = self._state
        # validation
        if index == -1:
            raise IndexError('list assignment index out of range. array is empty which means no past item exists')

        return array[index]

    def get_past_item(self, past_index) -> np.ndarray:
        array, index = self._state
        # validation
        if index == -1:
            raise IndexError('list assignment index out of range. array is empty which means no past item exists')
        # validation
        if (index - past_index) < 0:
            raise IndexError(f'list assignment index out of range. Max allowed is self.index={index}, past_index={past_index}')

        return array[index - past_index]

    def flush(self) -> None:
        self._state = (np.zeros(self.shape), -1)
        self.bucket_size = self.shape[0]

    def append_multiple(self, items: np.ndarray) -> None:
        n_new = len(items)
        array, current_index = self._state
        new_index = current_index + n_new

        # Prepare the complete batch before atomically publishing its state.
        if new_index + 1 > len(array):
            min_required = new_index + 1
            new_size = max(min_required, len(array) * 2, max(self.bucket_size, 1))
            new_shape = (new_size,) + tuple(array.shape[1:])
            new_array = np.zeros(new_shape, dtype=array.dtype)
            if current_index >= 0:
                new_array[:current_index + 1] = array[:current_index + 1]
            array = new_array

        # drop N% of the beginning values to free memory
        if (
            self.drop_at is not None
            and new_index != 0
            and (new_index + 1) % self.drop_at == 0
        ):
            shift_num = int(self.drop_at / 2)
            new_index -= shift_num
            array = np_shift(array, -shift_num)

        array[new_index - n_new + 1:new_index + 1] = items
        self._state = (array, new_index)

    def delete(self, index: int, axis=None) -> None:
        array, current_index = self._state
        array = np.delete(array, index, axis=axis)
        new_index = current_index - 1
        if array.shape[0] <= self.shape[0]:
            new_bucket = np.zeros(self.shape)
            array = np.concatenate((array, new_bucket), axis=0)
        self._state = (array, new_index)



