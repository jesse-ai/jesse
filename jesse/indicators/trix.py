from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def ema(data: np.ndarray, period: int) -> np.ndarray:
    alpha = 2 / (period + 1)
    N = len(data)
    t = np.arange(N).reshape(-1, 1)  # Shape (N, 1) for time index
    i = np.arange(N).reshape(1, -1)  # Shape (1, N) for index of data
    # Compute weights for positions where i <= t
    weights = np.where(i <= t, alpha * (1 - alpha)**(t - i), 0.0)
    # Override the weight for i==0 to account for the initial condition: EMA[0] = data[0]
    weights[:, 0] = (1 - alpha)**(t[:, 0])
    return weights.dot(data)


def trix(candles: np.ndarray, period: int = 18, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    TRIX - 1-day Rate-Of-Change (ROC) of a Triple Smooth EMA

    :param candles: np.ndarray
    :param period: int - default: 18
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    # Compute triple EMA on the logarithm of the source prices
    log_source = np.log(source)
    ema1 = ema(log_source, period)
    ema2 = ema(ema1, period)
    ema3 = ema(ema2, period)

    # Calculate the change (current ema3 minus previous ema3), prepending NaN to maintain same length
    diff = np.empty_like(ema3)
    diff[0] = np.nan
    diff[1:] = ema3[1:] - ema3[:-1]
    result = diff * 10000

    return result if sequential else result[-1]
