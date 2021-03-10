from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def sarext(candles: np.ndarray, start_value: float = 0, offset_on_reverse: float = 0, acceleration_init_long: float = 0,
           acceleration_long: float = 0, acceleration_max_long: float = 0, acceleration_init_short: float = 0,
           acceleration_short: float = 0, acceleration_max_short: float = 0, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    SAREXT - Parabolic SAR - Extended

    :param candles: np.ndarray
    :param start_value: float - default: 0
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
    candles = slice_candles(candles, sequential)

    res = talib.SAREXT(candles[:, 3], candles[:, 4], startvalue=start_value, offsetonreverse=offset_on_reverse,
                       accelerationinitlong=acceleration_init_long, accelerationlong=acceleration_long,
                       accelerationmaxlong=acceleration_max_long, accelerationinitshort=acceleration_init_short,
                       accelerationshort=acceleration_short, accelerationmaxshort=acceleration_max_short)

    return res if sequential else res[-1]
