from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles


def tsi(candles: np.ndarray, long_period: int = 25, short_period: int = 13, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
     True strength index (TSI)

    :param candles: np.ndarray
    :param long_period: int - default: 25
    :param short_period: int - default: 13
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    r = 100 * (talib.EMA((talib.EMA(talib.MOM(source, 1), long_period)), short_period)) / (
        talib.EMA((talib.EMA(np.absolute(talib.MOM(source, 1)), long_period)), short_period))

    return r if sequential else r[-1]
