from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

DonchianChannel = namedtuple('DonchianChannel', ['upperband', 'middleband', 'lowerband'])


def donchian(candles: np.ndarray, period: int = 20, sequential: bool = False) -> DonchianChannel:
    """
    Donchian Channels

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default: False

    :return: DonchianChannel(upperband, middleband, lowerband)
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]

    if sequential:
        # Compute rolling maximum and minimum using sliding_window_view, vectorized without explicit loops
        from numpy.lib.stride_tricks import sliding_window_view
        n = high.shape[0]
        # Prepare output arrays with NaN for the initial period-1 values
        rolling_max = np.empty(n)
        rolling_min = np.empty(n)
        rolling_max[:period - 1] = np.nan
        rolling_min[:period - 1] = np.nan
        # Compute sliding window view for the valid windows
        windowed_high = sliding_window_view(high, window_shape=period)
        windowed_low = sliding_window_view(low, window_shape=period)
        rolling_max[period - 1:] = np.max(windowed_high, axis=1)
        rolling_min[period - 1:] = np.min(windowed_low, axis=1)
        middleband = (rolling_max + rolling_min) / 2
        return DonchianChannel(rolling_max, middleband, rolling_min)
    else:
        # Non-sequential: compute only the last period's max and min
        uc = np.max(high[-period:])
        lc = np.min(low[-period:])
        mc = (uc + lc) / 2
        return DonchianChannel(uc, mc, lc)
