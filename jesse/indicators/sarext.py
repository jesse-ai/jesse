from typing import Union

import numpy as np
import talib


def sarext(candles: np.ndarray, startvalue=0, offsetonreverse=0, accelerationinitlong=0, accelerationlong=0,
           accelerationmaxlong=0, accelerationinitshort=0, accelerationshort=0, accelerationmaxshort=0,
           sequential=False) -> Union[float, np.ndarray]:
    """
    SAREXT - Parabolic SAR - Extended

    :param candles: np.ndarray
    :param startvalue: float - default: 0
    :param offsetonreverse: float - default: 0
    :param accelerationinitlong: float - default: 0
    :param accelerationlong: float - default: 0
    :param accelerationmaxlong: float - default: 0
    :param accelerationinitshort: float - default: 0
    :param accelerationshort: float - default: 0
    :param accelerationmaxshort: float - default: 0
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.SAREXT(candles[:, 3], candles[:, 4], startvalue=startvalue, offsetonreverse=offsetonreverse,
                       accelerationinitlong=accelerationinitlong, accelerationlong=accelerationlong,
                       accelerationmaxlong=accelerationmaxlong, accelerationinitshort=accelerationinitshort,
                       accelerationshort=accelerationshort, accelerationmaxshort=accelerationmaxshort)

    return res if sequential else res[-1]
