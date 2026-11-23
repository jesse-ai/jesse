from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

@overload
def adxr(candles: np.ndarray, period: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def adxr(candles: np.ndarray, period: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def adxr(candles: np.ndarray, period: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def adxr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """ADXR - Average Directional Movement Index Rating (TradingView variant).

    Uses the SMA and lag conventions of the Kivanc Ozbilgic script credited in
    Jesse's indicator reference:
    https://www.tradingview.com/script/9f5zDi3r/

    This variant takes a simple moving average of DX, then averages that series
    with its value ``period`` bars earlier. It does not use the Wilder-smoothed
    series returned by ``adx``. TA-Lib's ADXR also uses a different lag of
    ``period - 1`` bars, so its values are not interchangeable with this variant.
    """
    candles = slice_candles(candles, sequential)
    res = jr.adxr(np.ascontiguousarray(candles, dtype=np.float64), period)
    return res if sequential else res[-1]
