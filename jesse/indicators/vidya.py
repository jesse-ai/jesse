from typing import Union
import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, same_length, slice_candles


@njit
def vidya_numba(source: np.ndarray, length: int, fix_cmo: bool, select: bool) -> np.ndarray:
    alpha = 2 / (length + 1)
    momm = np.zeros_like(source)
    momm[1:] = source[1:] - source[:-1]
    momm[0] = 0

    # Initialize arrays for positive and negative momentum
    m1 = np.where(momm >= 0, momm, 0)
    m2 = np.where(momm < 0, -momm, 0)

    # Calculate rolling sums
    cmo_length = 9 if fix_cmo else length
    sm1 = np.zeros_like(source)
    sm2 = np.zeros_like(source)

    for i in range(len(source)):
        start_idx = max(0, i - cmo_length + 1)
        sm1[i] = np.sum(m1[start_idx:i+1])
        sm2[i] = np.sum(m2[start_idx:i+1])

    # Calculate Chande Momentum
    total_sum = sm1 + sm2
    chande_mo = np.where(total_sum != 0, 100 * (sm1 - sm2) / total_sum, 0)

    # Calculate k factor
    if select:
        k = np.abs(chande_mo) / 100
    else:
        k = np.zeros_like(source)
        for i in range(len(source)):
            start_idx = max(0, i - length + 1)
            k[i] = np.std(source[start_idx:i+1])

    # Calculate VIDYA
    vidya = np.zeros_like(source)
    vidya[0] = source[0]
    for i in range(1, len(source)):
        vidya[i] = alpha * k[i] * source[i] + (1 - alpha * k[i]) * vidya[i-1]

    return vidya


def vidya(candles: np.ndarray, length: int = 9, fix_cmo: bool = True, select: bool = True, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    VIDYA - Variable Index Dynamic Average

    :param candles: np.ndarray
    :param length: int - default: 9
    :param fix_cmo: bool - default: True    Fixed CMO Length (9)?
    :param select: bool - default: True     Calculation Method: CMO/StDev?
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = vidya_numba(source, length, fix_cmo, select)

    return same_length(candles, res) if sequential else res[-1]
