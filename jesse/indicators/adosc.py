from typing import Union

import numpy as np
from jesse.indicators.ema import ema
from jesse.helpers import slice_candles


def adosc(candles: np.ndarray, fast_period: int = 3, slow_period: int = 10, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    ADOSC - Chaikin A/D Oscillator

    :param candles: np.ndarray
    :param fast_period: int - default: 3
    :param slow_period: int - default: 10
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # Extract candle data: high, low, close, volume
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    volume = candles[:, 5]

    # Compute Money Flow Multiplier; avoid division by zero
    range_array = high - low
    multiplier = np.where(range_array != 0, ((close - low) - (high - close)) / range_array, 0.0)

    # Money Flow Volume
    mf_volume = multiplier * volume

    # AD line is the cumulative sum of Money Flow Volume
    ad_line = np.cumsum(mf_volume)

    # Compute fast and slow exponential moving averages of the AD line
    fast_ema = ema(ad_line, fast_period, sequential=True)
    slow_ema = ema(ad_line, slow_period, sequential=True)

    # AD Oscillator is the difference between fast EMA and slow EMA
    adosc_vals = fast_ema - slow_ema

    return adosc_vals if sequential else adosc_vals[-1]
