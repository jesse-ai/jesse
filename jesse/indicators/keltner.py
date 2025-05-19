from collections import namedtuple
import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma

KeltnerChannel = namedtuple('KeltnerChannel', ['upperband', 'middleband', 'lowerband'])


@njit
def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate ATR using Numba
    """
    n = len(close)
    tr = np.empty(n)
    atr_vals = np.full(n, np.nan)
    
    # Calculate True Range
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        tr[i] = max(max(hl, hc), lc)
    
    if n < period:
        return atr_vals
        
    # First ATR value is the simple average of the first 'period' true ranges
    atr_vals[period-1] = np.mean(tr[:period])
    
    # Calculate subsequent ATR values using Wilder's smoothing
    for i in range(period, n):
        atr_vals[i] = (atr_vals[i-1] * (period - 1) + tr[i]) / period
        
    return atr_vals


@njit
def _calculate_keltner(source: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray, 
                      ma_values: np.ndarray, period: int, multiplier: float) -> tuple:
    """
    Core Keltner Channel calculation using Numba
    """
    atr_vals = _atr(high, low, close, period)
    
    up = ma_values + atr_vals * multiplier
    low = ma_values - atr_vals * multiplier
    
    return up, ma_values, low


def keltner(candles: np.ndarray, period: int = 20, multiplier: float = 2, matype: int = 1, 
           source_type: str = "close", sequential: bool = False) -> KeltnerChannel:
    """
    Keltner Channels using Numba for optimization

    :param candles: np.ndarray
    :param period: int - default: 20
    :param multiplier: float - default: 2
    :param matype: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: KeltnerChannel(upperband, middleband, lowerband)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    if matype == 24 or matype == 29:
        ma_values = ma(candles, period=period, matype=matype, source_type=source_type, sequential=True)
    else:
        ma_values = ma(source, period=period, matype=matype, sequential=True)
    
    up, mid, low = _calculate_keltner(
        source, 
        candles[:, 3],  # high
        candles[:, 4],  # low
        candles[:, 2],  # close
        ma_values,
        period,
        multiplier
    )

    if sequential:
        return KeltnerChannel(up, mid, low)
    else:
        return KeltnerChannel(up[-1], mid[-1], low[-1])
