from typing import Union

import numpy as np
from jesse.helpers import get_candle_source, slice_candles


def tsi(candles: np.ndarray, long_period: int = 25, short_period: int = 13, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
     True strength index (TSI)

    :param candles: np.ndarray
    :param long_period: int - default: 25
    :param short_period: int - default: 13
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    mom = _mom(source, 1)
    ema_mom = _ema(mom, long_period)
    double_ema_mom = _ema(ema_mom, short_period)

    ema_abs_mom = _ema(np.abs(mom), long_period)
    double_ema_abs_mom = _ema(ema_abs_mom, short_period)

    # Avoid division by zero and invalid results
    with np.errstate(divide='ignore', invalid='ignore'):
        r = 100 * double_ema_mom / double_ema_abs_mom
        r[~np.isfinite(r)] = 0

    return r if sequential else r[-1]


def _mom(series, period):
    # Calculate momentum as difference between current and period ago value
    return np.concatenate((np.zeros(period), series[period:] - series[:-period]))

def _ema(series, period):
    # Exponential Moving Average using a vectorized approach with convolution
    alpha = 2 / (period + 1)
    n = len(series)
    t_arr = np.arange(n)
    # Calculate the contribution from the first element
    ema_vals = series[0] * ((1 - alpha) ** t_arr)
    if n > 1:
        # For t>=1, add the convolution of the rest of the series with the weights alpha*(1-alpha)^(t)
        conv = np.convolve(series[1:], alpha * ((1 - alpha) ** np.arange(n - 1)), mode='full')[:n-1]
        ema_vals[1:] += conv
    return ema_vals
