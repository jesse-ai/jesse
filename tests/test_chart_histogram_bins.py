import numpy as np

from jesse.services.charts import MAX_HISTOGRAM_BINS, _histogram_bin_count


def test_small_samples_use_fixed_bins():
    assert _histogram_bin_count(np.array([1.0, 2.0, 3.0])) == 10


def test_zero_iqr_uses_fixed_bins():
    assert _histogram_bin_count(np.array([-2.5] * 39 + [250.0])) == 15


def test_freedman_diaconis_unchanged_for_normal_data():
    arr = np.linspace(-10, 10, 100)
    q75, q25 = np.percentile(arr, [75, 25])
    expected = max(5, int(np.ceil(20 / (2 * (q75 - q25) * 100 ** (-1 / 3)))))
    assert _histogram_bin_count(arr) == expected < MAX_HISTOGRAM_BINS


def test_tiny_iqr_with_outlier_is_capped():
    # Reproduction from #641: 39 near-identical stop-outs plus one large winner.
    arr = np.array([-2.5 + i * 1e-9 for i in range(39)] + [250.0])
    assert _histogram_bin_count(arr) == MAX_HISTOGRAM_BINS
    counts, _ = np.histogram(arr, bins=_histogram_bin_count(arr))
    assert counts.sum() == len(arr)
