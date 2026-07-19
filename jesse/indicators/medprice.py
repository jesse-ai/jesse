from typing import Literal, Union, overload

import numpy as np

from jesse.helpers import slice_candles


@overload
def medprice(candles: np.ndarray, sequential: Literal[False] = ...) -> float: ...
@overload
def medprice(candles: np.ndarray, sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def medprice(candles: np.ndarray, sequential: bool = ...) -> Union[float, np.ndarray]: ...

def medprice(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    MEDPRICE - Median Price

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = (candles[:, 3] + candles[:, 4]) / 2

    return res if sequential else res[-1]
