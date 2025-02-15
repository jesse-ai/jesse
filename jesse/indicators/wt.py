from collections import namedtuple
import numpy as np
from numba import jit
from jesse.helpers import get_candle_source, slice_candles

Wavetrend = namedtuple('Wavetrend', ['wt1', 'wt2', 'wtCrossUp', 'wtCrossDown', 'wtOversold', 'wtOverbought', 'wtVwap'])


# Wavetrend indicator ported from:  https://www.tradingview.com/script/Msm4SjwI-VuManChu-Cipher-B-Divergences/
#                                   https://www.tradingview.com/script/2KE8wTuF-Indicator-WaveTrend-Oscillator-WT/
#
# buySignal = wtCross and wtCrossUp and wtOversold
# sellSignal = wtCross and wtCrossDown and wtOverbought
#
# See https://github.com/ysdede/lazarus3/blob/partialexit/strategies/lazarus3/__init__.py for working jesse.ai example.

@jit(cache=True)
def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate EMA using Numba-optimized implementation
    """
    alpha = 2.0 / (period + 1.0)
    result = np.zeros_like(arr)
    result[0] = arr[0]
    
    for i in range(1, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i-1]
    
    return result

@jit(cache=True)
def _sma(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate SMA using Numba-optimized implementation
    """
    result = np.zeros_like(arr)
    
    # Handle first period-1 elements
    cumsum = 0.0
    for i in range(period-1):
        cumsum += arr[i]
        result[i] = cumsum / (i + 1)
    
    # Handle remaining elements with sliding window
    cumsum = sum(arr[0:period])
    result[period-1] = cumsum / period
    
    for i in range(period, len(arr)):
        cumsum = cumsum - arr[i-period] + arr[i]
        result[i] = cumsum / period
    
    return result

@jit(cache=True)
def _fast_wt(src: np.ndarray, wtchannellen: int, wtaveragelen: int, wtmalen: int) -> tuple:
    """
    Calculate Wavetrend components using Numba
    """
    esa = _ema(src, wtchannellen)
    
    # Calculate absolute difference
    abs_diff = np.abs(src - esa)
    de = _ema(abs_diff, wtchannellen)
    
    # Avoid division by zero
    de = np.where(de == 0, 1e-10, de)
    ci = (src - esa) / (0.015 * de)
    
    wt1 = _ema(ci, wtaveragelen)
    wt2 = _sma(wt1, wtmalen)
    
    return wt1, wt2

def wt(candles: np.ndarray, wtchannellen: int = 9, wtaveragelen: int = 12, wtmalen: int = 3, oblevel: int = 53, oslevel: int = -53, source_type: str = "hlc3", sequential: bool = False) -> Wavetrend:
    """
    Wavetrend indicator

    :param candles: np.ndarray
    :param wtchannellen:  int - default: 9
    :param wtaveragelen: int - default: 12
    :param wtmalen: int - default: 3
    :param oblevel: int - default: 53
    :param oslevel: int - default: -53
    :param source_type: str - default: "hlc3"
    :param sequential: bool - default: False

    :return: Wavetrend
    """
    candles = slice_candles(candles, sequential)
    src = get_candle_source(candles, source_type=source_type)
    
    # Convert inputs to float64 for better numerical stability
    src = src.astype(np.float64)
    
    # Calculate main components
    wt1, wt2 = _fast_wt(src, wtchannellen, wtaveragelen, wtmalen)
    
    # Calculate additional components
    wtVwap = wt1 - wt2
    wtOversold = wt2 <= oslevel
    wtOverbought = wt2 >= oblevel
    wtCrossUp = wt2 - wt1 <= 0
    wtCrossDown = wt2 - wt1 >= 0

    if sequential:
        return Wavetrend(wt1, wt2, wtCrossUp, wtCrossDown, wtOversold, wtOverbought, wtVwap)
    else:
        return Wavetrend(wt1[-1], wt2[-1], wtCrossUp[-1], wtCrossDown[-1], wtOversold[-1], wtOverbought[-1], wtVwap[-1])
