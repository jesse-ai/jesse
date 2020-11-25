import talib
from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source

DamianiVolatmeter = namedtuple('DamianiVolatmeter', ['vol', 'anti' ])


def damiani_volatmeter(candles: np.ndarray, vis_atr=13, vis_std=20, sed_atr=40, sed_std=100, threshold=1.4, source_type="close", sequential=False) -> DamianiVolatmeter:
    """
    Damiani Volatmeter

    :param candles: np.ndarray
    :param vis_atr: int - default=13
    :param vis_std: int - default=20
    :param sed_atr: int - default=40
    :param sed_std: int - default=100
    :param threshold: float - default=1.4
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    lag_s = 0.5

    vol = np.full_like(source, 0)
    t = np.full_like(source, 0)

    atrvis = talib.ATR(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=vis_atr)
    atrsed = talib.ATR(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=sed_atr)

    for i in range(source.shape[0]):
        if not (i < sed_std):
            vol[i]=atrvis[i] / atrsed[i] + lag_s * (vol[i - 1] - vol[i - 3])
            anti_thres = np.std(source[i - vis_std:i]) / np.std(source[i - sed_std:i])
            t[i] = threshold - anti_thres

    if sequential:
        return DamianiVolatmeter(vol, t)
    else:
        return DamianiVolatmeter(vol[-1], t[-1])
