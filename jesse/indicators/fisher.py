from collections import namedtuple
import numpy as np
from numba import njit
from jesse.helpers import same_length, slice_candles

FisherTransform = namedtuple('FisherTransform', ['fisher', 'signal'])


@njit
def _fisher_transform(high: np.ndarray, low: np.ndarray, period: int) -> tuple:
    """
    Numba-optimized implementation of Fisher Transform
    """
    length = len(high)
    mid_price = (high + low) / 2
    fisher = np.zeros(length)
    fisher_signal = np.zeros(length)

    # Initialize first value
    value1 = 0.0

    for i in range(period, length):
        # Find the highest high and lowest low in the period
        max_h = np.max(mid_price[i-period+1:i+1])
        min_l = np.min(mid_price[i-period+1:i+1])

        # Avoid division by zero
        if max_h - min_l == 0:
            value0 = 0
        else:
            value0 = 0.33 * 2 * ((mid_price[i] - min_l) / (max_h - min_l) - 0.5) + 0.67 * value1

        if value0 > 0.99:
            value0 = 0.999
        elif value0 < -0.99:
            value0 = -0.999

        fisher[i] = 0.5 * np.log((1 + value0) / (1 - value0)) + 0.5 * fisher[i-1]
        fisher_signal[i] = fisher[i-1]
        value1 = value0

    return fisher, fisher_signal


def fisher(candles: np.ndarray, period: int = 9, sequential: bool = False) -> FisherTransform:
    """
    The Fisher Transform helps identify price reversals.

    :param candles: np.ndarray
    :param period: int - default: 9
    :param sequential: bool - default: False

    :return: FisherTransform(fisher, signal)
    """
    candles = slice_candles(candles, sequential)

    fisher_val, fisher_signal = _fisher_transform(
        np.ascontiguousarray(candles[:, 3]),
        np.ascontiguousarray(candles[:, 4]),
        period
    )

    if sequential:
        return FisherTransform(same_length(candles, fisher_val), same_length(candles, fisher_signal))
    else:
        return FisherTransform(fisher_val[-1], fisher_signal[-1])
