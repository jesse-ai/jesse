from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def ad(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    AD - Chaikin A/D Line

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3].astype(np.float64)
    low = candles[:, 4].astype(np.float64)
    close = candles[:, 2].astype(np.float64)
    volume = candles[:, 5].astype(np.float64)

    # Calculate Money Flow Multiplier. Safeguard division by zero in case high equals low.
    mfm = np.where(high != low, ((close - low) - (high - close)) / (high - low), 0.0)

    # Calculate Money Flow Volume
    mfv = mfm * volume

    # Compute the Accumulation/Distribution line as the cumulative sum of Money Flow Volume
    ad_line = np.cumsum(mfv)

    return ad_line if sequential else ad_line[-1]
