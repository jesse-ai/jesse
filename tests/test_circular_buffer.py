from jesse.libs import CircularBuffer
import numpy as np
import pytest


def test_append():
    a = CircularBuffer(size=6)
    with pytest.raises(IndexError):
        a[0] is None
    with pytest.raises(IndexError):
        a[-1] is None
    assert len(a) == 0
    a.append(np.array([1, 2, 3, 4, 5, 6]))
    assert a[0][0] == 1
    assert a[0][1] == 2
    assert a[0][2] == 3
    assert a[0][3] == 4
    assert a[0][4] == 5
    assert a[0][5] == 6
    assert a[-1][0] == 1
    assert len(a) == 1

    a.append(np.array([7, 8, 9, 10, 11, 12]))
    assert a[1][0] == 7
    assert a[1][1] == 8
    assert a[1][2] == 9
    assert a[1][3] == 10
    assert a[1][4] == 11
    assert a[1][5] == 12
    assert a[-1][0] == 7
    assert len(a) == 2

    np.testing.assert_array_equal(a[0][:], np.array([1, 2, 3, 4, 5, 6]))
    np.testing.assert_array_equal(a[1][:], np.array([7, 8, 9, 10, 11, 12]))

def test_circular_append():
    a = CircularBuffer(size=6)
    count = 0
    for idx, i in enumerate(range(1, 10)):
        a.append(i)
        count += 1
        assert len(a) == min(count, 6)
        assert a[-1] == i
    assert a[0] == 4
    assert a[-1] == 9

def test_slicing(): # Slicing is slow and not recommended
    a = CircularBuffer(size=6)
    for _, i in enumerate(range(1, 10)):
        a.append(i)
    assert a[:] == [4, 5, 6, 7, 8, 9]
    assert a[::2] == [4, 6, 8]
    assert a[1:3] == [5, 6]
    with pytest.raises(ValueError):
        a[::0] is None

def test_clear():
    a = CircularBuffer(size=6)
    for _, i in enumerate(range(1, 10)):
        a.append(i)
    assert a[0] == 4
    assert a[-1] == 9
    a.clear()
    with pytest.raises(IndexError):
        a[0] is None
    with pytest.raises(IndexError):
        a[-1] is None
    len(a) == 0
    for _, i in enumerate(range(1, 10)):
        a.append(i)
    assert a[0] == 4
    assert a[-1] == 9

def test_iter():
    a = CircularBuffer(size=6)
    for _, i in enumerate(range(1, 10)):
        a.append(i)
    count = 4
    for item in a:
        assert count == item
        count += 1

def test_wrap():
    a = CircularBuffer(size=5)

    assert a.wrap_len == 0
    for i in range(5):
        a.append(i)
    assert a.wrap_len == 5

    for i in range(2):
        a.append(i)
    assert a.wrap_len == 2