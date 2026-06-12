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
    """Verify the buffer grows to accommodate appends.

    The exact post-grow shape is an implementation detail (linear-bucket vs
    geometric); what matters behaviorally is that all appended values are
    retained correctly and the buffer has at least enough capacity.
    """
    a = DynamicNumpyArray((3, 6))

    assert a.array.shape == (3, 6)

    a.append(np.array([1, 2, 3, 4, 5, 6]))
    a.append(np.array([7, 8, 9, 10, 11, 12]))
    a.append(np.array([13, 14, 15, 16, 17, 18]))
    assert a.array.shape[0] >= 3
    assert a.array.shape[1] == 6
    assert a.index == 2
    np.testing.assert_array_equal(a[0], np.array([1, 2, 3, 4, 5, 6]))
    np.testing.assert_array_equal(a[2], np.array([13, 14, 15, 16, 17, 18]))

    a.append(np.array([19, 20, 21, 22, 23, 24]))
    a.append(np.array([25, 26, 27, 28, 29, 30]))
    a.append(np.array([31, 32, 33, 34, 35, 36]))
    assert a.array.shape[0] >= 6
    assert a.array.shape[1] == 6
    assert a.index == 5
    np.testing.assert_array_equal(a[5], np.array([31, 32, 33, 34, 35, 36]))


def test_geometric_growth_pattern():
    """The number of buffer reallocations across N appends should be O(log N),
    not O(N/bucket_size). This guards against accidental regression to linear
    growth (which produces O(N^2) total memcpy on long backtests)."""
    a = DynamicNumpyArray((4, 6))
    n_appends = 5000

    sizes_seen = [a.array.shape[0]]
    for i in range(n_appends):
        a.append(np.array([i, i + 1, i + 2, i + 3, i + 4, i + 5]))
        if a.array.shape[0] != sizes_seen[-1]:
            sizes_seen.append(a.array.shape[0])

    # log2(5000/4) ≈ 10.3 — we should see at most ~12 distinct sizes.
    assert len(sizes_seen) <= 14, (
        f"too many growths ({len(sizes_seen)}): {sizes_seen}"
    )
    # Each growth at least 1.5× the prior — prevents accidental linear growth
    for prev, nxt in zip(sizes_seen, sizes_seen[1:]):
        assert nxt >= prev * 1.5, (
            f"growth from {prev} to {nxt} is sub-geometric"
        )

    # Spot-check correctness — appends should be intact in order
    np.testing.assert_array_equal(a[0], np.array([0, 1, 2, 3, 4, 5]))
    np.testing.assert_array_equal(a[2500], np.array([2500, 2501, 2502, 2503, 2504, 2505]))
    np.testing.assert_array_equal(a[n_appends - 1], np.array([4999, 5000, 5001, 5002, 5003, 5004]))


def test_append_multiple_grows_geometrically():
    """append_multiple should also use geometric growth and produce identical
    final state to the equivalent sequence of append() calls."""
    via_multiple = DynamicNumpyArray((10, 6))
    via_single = DynamicNumpyArray((10, 6))

    rng = np.random.default_rng(seed=42)
    n_batches = 30
    batch_size = 25
    for _ in range(n_batches):
        batch = rng.standard_normal((batch_size, 6))
        via_multiple.append_multiple(batch)
        for row in batch:
            via_single.append(row)

    assert via_multiple.index == via_single.index
    np.testing.assert_array_equal(
        via_multiple.array[:via_multiple.index + 1],
        via_single.array[:via_single.index + 1],
    )


def test_append_multiple_varied_batch_sizes():
    """append_multiple must hold the correct valid data regardless of batch
    sizes relative to the bucket size (small, equal, and much larger batches),
    including a single batch larger than the current capacity."""
    a = DynamicNumpyArray((10, 6))
    expected = []
    rng = np.random.default_rng(seed=7)
    for bs in [1, 5, 10, 23, 100, 3, 50, 7, 200]:
        batch = rng.standard_normal((bs, 6))
        a.append_multiple(batch)
        expected.extend(batch.tolist())

    assert a.index == len(expected) - 1
    np.testing.assert_array_equal(a.array[:a.index + 1], np.array(expected))
    # capacity must always be large enough to hold the valid region
    assert a.array.shape[0] >= a.index + 1


def test_geometric_growth_never_overflows():
    """After every append the write index must remain within capacity — guards
    against an off-by-one in the doubling condition."""
    a = DynamicNumpyArray((4, 6))
    for i in range(3000):
        a.append(np.arange(6, dtype=float) + i)
        assert a.index < a.array.shape[0]
    np.testing.assert_array_equal(a[2999], np.arange(6, dtype=float) + 2999)


def test_append_multiple_then_append_no_overflow():
    """Mirror the real backtest flow: candles are warmed up in chunks via
    append_multiple() and then streamed in one-by-one via append() on the SAME
    storage (see candle_service.add_multiple_1m_candles -> add_candle).

    The previous linear-bucket implementation assumed capacity stayed a
    multiple of bucket_size, an invariant append_multiple could break, so a
    chunked warmup (e.g. 1500 + 800 into a bucket_size=1000 array) followed by
    single appends overflowed with an IndexError. Geometric growth keys off the
    actual capacity, so it must keep correct data without ever overflowing.
    """
    a = DynamicNumpyArray((1000, 6))
    expected = []

    # chunked warmup via append_multiple
    for chunk in (1500, 800):
        batch = np.arange(len(expected) * 6, (len(expected) + chunk) * 6, dtype=float).reshape(chunk, 6)
        a.append_multiple(batch)
        expected.extend(batch.tolist())

    # then stream single candles in, well past the warmed-up capacity
    for i in range(5000):
        row = np.full(6, 1_000_000.0 + i)
        a.append(row)
        expected.append(row.tolist())
        # the write index must always stay within the allocated buffer
        assert a.index < a.array.shape[0]

    assert a.index == len(expected) - 1
    np.testing.assert_array_equal(a.array[:a.index + 1], np.array(expected))
    np.testing.assert_array_equal(a[0], np.array([0, 1, 2, 3, 4, 5], dtype=float))
    np.testing.assert_array_equal(a[-1], np.full(6, 1_000_000.0 + 4999))


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

