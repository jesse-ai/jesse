from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def adx(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ADX - Average Directional Movement Index (manual implementation without TA-Lib)

    :param candles: np.ndarray, expected 2D array with OHLCV data where index 3 is high, index 4 is low, and index 2 is close
    :param period: int - default: 14
    :param sequential: bool - if True, return full series, else return last value

    :return: float | np.ndarray
    """
    if len(candles.shape) < 2:
        raise ValueError("adx indicator requires a 2D array of candles")
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    n = len(close)
    if n <= period:
         return np.nan if sequential else np.nan

    TR = np.zeros(n)
    plusDM = np.zeros(n)
    minusDM = np.zeros(n)
    for i in range(1, n):
         current_high = high[i]
         current_low = low[i]
         prev_high = high[i-1]
         prev_low = low[i-1]
         prev_close = close[i-1]
         TR[i] = max(current_high - current_low, abs(current_high - prev_close), abs(current_low - prev_close))
         move_up = current_high - prev_high
         move_down = prev_low - current_low
         plusDM[i] = move_up if (move_up > move_down and move_up > 0) else 0
         minusDM[i] = move_down if (move_down > move_up and move_down > 0) else 0

    # Wilder's smoothing for TR, plusDM, and minusDM
    tr_smoothed = np.zeros(n)
    plusDM_smoothed = np.zeros(n)
    minusDM_smoothed = np.zeros(n)

    # Initialize the smoothed values with the sum of the first 'period' values (starting from index 1)
    tr_smoothed[period] = np.sum(TR[1:period+1])
    plusDM_smoothed[period] = np.sum(plusDM[1:period+1])
    minusDM_smoothed[period] = np.sum(minusDM[1:period+1])

    for i in range(period+1, n):
         tr_smoothed[i] = tr_smoothed[i-1] - (tr_smoothed[i-1] / period) + TR[i]
         plusDM_smoothed[i] = plusDM_smoothed[i-1] - (plusDM_smoothed[i-1] / period) + plusDM[i]
         minusDM_smoothed[i] = minusDM_smoothed[i-1] - (minusDM_smoothed[i-1] / period) + minusDM[i]

    DI_plus = np.zeros(n)
    DI_minus = np.zeros(n)
    DX = np.zeros(n)
    for i in range(period, n):
         if tr_smoothed[i] == 0:
             DI_plus[i] = 0
             DI_minus[i] = 0
         else:
             DI_plus[i] = 100 * (plusDM_smoothed[i] / tr_smoothed[i])
             DI_minus[i] = 100 * (minusDM_smoothed[i] / tr_smoothed[i])

         dd = DI_plus[i] + DI_minus[i]
         DX[i] = 0 if dd == 0 else 100 * abs(DI_plus[i] - DI_minus[i]) / dd

    # Calculate ADX as the smoothed average of DX values
    ADX = np.full(n, np.nan)
    start_index = period * 2  # first valid ADX index (0-indexed)
    if start_index < n:
         first_adx = np.mean(DX[period:start_index])
         ADX[start_index] = first_adx
         for i in range(start_index+1, n):
              ADX[i] = ((ADX[i-1] * (period - 1)) + DX[i]) / period
         result = ADX if sequential else ADX[n-1]
    else:
         result = np.nan
    return result
