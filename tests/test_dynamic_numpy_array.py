import numpy as np
import pytest

from jesse.libs import DynamicNumpyArray


def test_append():
    a = DynamicNumpyArray((10, 6))
    a.append(np.array([1, 2, 3, 4, 5, 6]))
    assert a.index == 0
    assert a.array[0][0] == 1
    assert a.array[0][1] == 2
    assert a.array[0][2] == 3
    assert a.array[0][3] == 4
    assert a.array[0][4] == 5
    assert a.array[0][5] == 6

    a.append(np.array([7, 8, 9, 10, 11, 12]))
    assert a.index == 1
    assert a.array[1][0] == 7
    assert a.array[1][1] == 8
    assert a.array[1][2] == 9
    assert a.array[1][3] == 10
    assert a.array[1][4] == 11
    assert a.array[1][5] == 12


def test_flush():
    a = DynamicNumpyArray((10, 6))
    a.append(np.array([1, 2, 3, 4, 5, 6]))
    a.append(np.array([7, 8, 9, 10, 11, 12]))
    assert a.index == 1
    assert a.array[0][0] == 1
    assert a.array[1][0] == 7

    a.flush()

    assert a.index == -1
    assert a.array[0][0] == 0
    assert a.array[1][0] == 0


def test_get_last_item():
    a = DynamicNumpyArray((10, 6))

    with pytest.raises(IndexError):
        a.get_last_item()

    a.append(np.array([1, 2, 3, 4, 5, 6]))
    a.append(np.array([7, 8, 9, 10, 11, 12]))
    assert a.index == 1
    assert a.array[0][0] == 1
    assert a.array[1][0] == 7

    np.testing.assert_array_equal(a.get_last_item(), np.array([7, 8, 9, 10, 11, 12]))


def test_get_past_item():
    a = DynamicNumpyArray((10, 6))

    with pytest.raises(IndexError):
        a.get_past_item(1)

    a.append(np.array([1, 2, 3, 4, 5, 6]))
    a.append(np.array([7, 8, 9, 10, 11, 12]))
    assert a.index == 1
    assert a.array[0][0] == 1
    assert a.array[1][0] == 7

    np.testing.assert_array_equal(a.get_past_item(1), np.array([1, 2, 3, 4, 5, 6]))

    with pytest.raises(IndexError):
        a.get_past_item(2)


def test_get_item():
    a = DynamicNumpyArray((10, 6))

    # test getting while array is empty
    with pytest.raises(IndexError):
        var = a[0]

    a.append(np.array([1, 2, 3, 4, 5, 6]))
    a.append(np.array([7, 8, 9, 10, 11, 12]))
    assert a.index == 1
    assert a.array[0][0] == 1
    assert a.array[1][0] == 7

    np.testing.assert_array_equal(a[0], np.array([1, 2, 3, 4, 5, 6]))
    np.testing.assert_array_equal(a[1], np.array([7, 8, 9, 10, 11, 12]))

    # test with an index that is out of range
    with pytest.raises(IndexError):
        var = a[2]


def test_array_size_increases():
    a = DynamicNumpyArray((3, 6))

    assert a.array.shape == (3, 6)

    a.append(np.array([1, 2, 3, 4, 5, 6]))
    a.append(np.array([7, 8, 9, 10, 11, 12]))
    a.append(np.array([13, 14, 15, 16, 17, 18]))
    assert a.array.shape == (6, 6)
    assert a.index == 2

    a.append(np.array([19, 20, 21, 22, 23, 24]))
    a.append(np.array([25, 26, 27, 28, 29, 30]))
    a.append(np.array([31, 32, 33, 34, 35, 36]))
    assert a.array.shape == (9, 6)
    assert a.index == 5


def test_drop_at():
    a = DynamicNumpyArray((100, 6), drop_at=6)

    # add 5 items
    a.append(np.array([1, 2, 3, 4, 5, 6]))
    a.append(np.array([7, 8, 9, 10, 11, 12]))
    a.append(np.array([13, 14, 15, 16, 17, 18]))
    a.append(np.array([19, 20, 21, 22, 23, 24]))
    a.append(np.array([25, 26, 27, 28, 29, 30]))
    assert a.get_last_item()[0] == 25
    assert a[0][0] == 1

    # add 6th item. when it reaches the drop_at limit, it should drop drop_at/2 items
    a.append(np.array([31, 32, 33, 34, 35, 36]))
    assert a[0][0] == 19

