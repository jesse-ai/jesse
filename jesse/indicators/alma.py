from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def alma(candles: np.ndarray, period: int = 9, sigma: float = 6.0, distribution_offset: float = 0.85,
         source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    ALMA - Arnaud Legoux Moving Average

    :param candles: np.ndarray
    :param period: int - default: 9
    :param sigma: float - default: 6.0
    :param distribution_offset: float - default: 0.85
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    asize = period - 1
    m = distribution_offset * asize
    s = period / sigma
    dss = 2 * s * s

    wtds = np.exp(-(np.arange(period) - m) ** 2 / dss)
    pnp_array3D = strided_axis0(source, len(wtds))
    res = np.zeros(source.shape)
    res[period - 1:] = np.tensordot(pnp_array3D, wtds, axes=(1, 0))[:]
    res /= wtds.sum()
    res[res == 0] = np.nan


    return res if sequential else res[-1]


def strided_axis0(a, L):
    # Store the shape and strides info
    shp = a.shape
    s = a.strides
    # Compute length of output array along the first axis
    nd0 = shp[0] - L + 1
    # Setup shape and strides for use with np.lib.stride_tricks.as_strided
    # and get (n+1) dim output array
    shp_in = (nd0, L) + shp[1:]
    strd_in = (s[0],) + s
    return np.lib.stride_tricks.as_strided(a, shape=shp_in, strides=strd_in)
