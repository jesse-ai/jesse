from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

DamianiVolatmeter = namedtuple('DamianiVolatmeter', ['vol', 'anti'])


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, timeperiod: int) -> np.ndarray:
    tr = np.empty_like(high, dtype=float)
    tr[0] = high[0] - low[0]
    if high.shape[0] > 1:
        diff1 = high[1:] - low[1:]
        diff2 = np.abs(high[1:] - close[:-1])
        diff3 = np.abs(low[1:] - close[:-1])
        tr[1:] = np.maximum(diff1, np.maximum(diff2, diff3))
    atr_array = np.full(high.shape, np.nan, dtype=float)
    if high.shape[0] < timeperiod:
        atr_array[-1] = np.mean(tr)
        return atr_array
    n = high.shape[0]
    m = n - timeperiod + 1
    alpha = 1.0 / timeperiod
    initial = np.mean(tr[:timeperiod])
    ema_vector = np.empty(m)
    ema_vector[0] = initial
    if m > 1:
        k = np.arange(m)  # k = 0,..., m-1
        initial_contrib = initial * (1 - alpha) ** k
        # Build a lower-triangular matrix for weights for indices 1 to m-1
        exp_matrix = np.tril((1 - alpha) ** (np.subtract.outer(np.arange(m - 1), np.arange(m - 1))))
        # tr[timeperiod:] has length m-1
        sum_vals = alpha * (exp_matrix @ tr[timeperiod:])
        ema_vector[1:] = initial_contrib[1:] + sum_vals
    atr_array[:timeperiod - 1] = np.nan
    atr_array[timeperiod - 1:] = ema_vector
    return atr_array

def damiani_volatmeter(candles: np.ndarray, vis_atr: int = 13, vis_std: int = 20, sed_atr: int = 40, sed_std: int = 100,
                       threshold: float = 1.4, source_type: str = "close",
                       sequential: bool = False) -> DamianiVolatmeter:
    """
    Damiani Volatmeter

    :param candles: np.ndarray
    :param vis_atr: int - default: 13
    :param vis_std: int - default: 20
    :param sed_atr: int - default: 40
    :param sed_std: int - default: 100
    :param threshold: float - default: 1.4
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    atrvis = atr(candles[:, 3], candles[:, 4], candles[:, 2], vis_atr)
    atrsed = atr(candles[:, 3], candles[:, 4], candles[:, 2], sed_atr)

    vol, t = damiani_volatmeter_fast(source, sed_std, atrvis, atrsed, vis_std, threshold)

    if sequential:
        return DamianiVolatmeter(vol, t)
    else:
        return DamianiVolatmeter(vol[-1], t[-1])

def damiani_volatmeter_fast(source, sed_std, atrvis, atrsed, vis_std, threshold):
    from scipy.signal import lfilter
    from numpy.lib.stride_tricks import sliding_window_view

    lag_s = 0.5
    n = source.shape[0]

    # Compute vol using a linear filter to solve the recurrence:
    # vol[i] - lag_s*vol[i-1] + lag_s*vol[i-3] = atrvis[i]/atrsed[i]
    u = np.zeros(n)
    u[sed_std:] = atrvis[sed_std:] / atrsed[sed_std:]
    b = [1.0]
    a = [1.0, -lag_s, 0.0, lag_s]
    vol = lfilter(b, a, u)

    # Compute t vectorized by calculating moving standard deviations without loops
    t = np.zeros(n)
    if n >= sed_std:
        std_vis = np.std(sliding_window_view(source, vis_std), axis=-1)
        std_sed = np.std(sliding_window_view(source, sed_std), axis=-1)
        idx = np.arange(sed_std, n)
        t[idx] = threshold - (std_vis[idx - vis_std] / std_sed[idx - sed_std])
    return vol, t
