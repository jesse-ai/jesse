from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def ema(series: np.ndarray, period: int) -> np.ndarray:
    """Calculates the Exponential Moving Average (EMA) for a series using a simple recursive formula."""
    alpha = 2 / (period + 1)
    out = np.empty_like(series, dtype=float)
    out[0] = series[0]
    for i in range(1, len(series)):
        out[i] = alpha * series[i] + (1 - alpha) * out[i - 1]
    return out


def stoch(series: np.ndarray, period: int) -> np.ndarray:
    """Calculates the stochastic oscillator for a series over the specified period."""
    result = np.full_like(series, np.nan, dtype=float)
    for i in range(len(series)):
        if i < period - 1:
            result[i] = np.nan
        else:
            window = series[i - period + 1: i + 1]
            low = np.min(window)
            high = np.max(window)
            if high == low:
                result[i] = 0
            else:
                result[i] = 100 * ((series[i] - low) / (high - low))
    return result


def stc(candles: np.ndarray, fast_period: int = 23, slow_period: int = 50, k_period: int = 10, d1_period: int = 3, d2_period: int = 3,
        source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    STC - Schaff Trend Cycle (Oscillator)

    The indicator is computed as follows:
    1. macd = EMA(src, fast_period) - EMA(src, slow_period)
    2. k = stoch(macd, k_period) with NaNs replaced by 0
    3. d   = EMA(k, d1_period)  -> First %D
    4. kd  = stoch(d, k_period) with NaNs replaced by 0
    5. stc_val = EMA(kd, d2_period) clamped between 0 and 100

    :param candles: np.ndarray of candles
    :param fast_period: int - default: 23
    :param slow_period: int - default: 50
    :param k_period: int - default: 10, cycle length for stoch computation
    :param d1_period: int - default: 3, used for first EMA smoothing of k
    :param d2_period: int - default: 3, used for EMA smoothing of kd
    :param source_type: str - default: "close"
    :param sequential: bool - default: False. When False, returns only the last value.
    :return: float or np.ndarray depending on sequential
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    ema_fast = ema(source, fast_period)
    ema_slow = ema(source, slow_period)
    macd = ema_fast - ema_slow

    k = stoch(macd, k_period)
    k = np.nan_to_num(k, nan=0)

    d_val = ema(k, d1_period)
    kd = stoch(d_val, k_period)
    kd = np.nan_to_num(kd, nan=0)

    stc_val = ema(kd, d2_period)
    stc_val = np.clip(stc_val, 0, 100)

    return stc_val if sequential else stc_val[-1]
    