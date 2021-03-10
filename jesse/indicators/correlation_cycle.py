from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, np_shift, slice_candles

CC = namedtuple('CC', ['real', 'imag', 'angle', 'state'])


def correlation_cycle(candles: np.ndarray, period: int = 20, threshold: int = 9, source_type: str = "close",
                      sequential: bool = False) -> CC:
    """
    "Correlation Cycle, Correlation Angle, Market State - John Ehlers

    :param candles: np.ndarray
    :param period: int - default: 20
    :param threshold: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: CC(real, imag)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    realPart, imagPart, angle = go_fast(source, period, threshold)

    priorAngle = np_shift(angle, 1, fill_value=np.nan)
    angle = np.where(np.logical_and(priorAngle > angle, priorAngle - angle < 270.0), priorAngle, angle)

    # Market State Function
    state = np.where(np.abs(angle - priorAngle) < threshold, np.where(angle >= 0.0, 1, np.where(angle < 0.0, -1, 0)), 0)

    if sequential:
        return CC(realPart, imagPart, angle, state)
    else:
        return CC(realPart[-1], imagPart[-1], angle[-1], state[-1])


@njit
def go_fast(source, period, threshold):  # Function is compiled to machine code when called the first time
    # Correlation Cycle Function
    PIx2 = 4.0 * np.arcsin(1.0)
    period = max(2, period)

    realPart = np.full_like(source, np.nan)
    imagPart = np.full_like(source, np.nan)

    for i in range(period, source.shape[0]):
        Rx = 0.0
        Rxx = 0.0
        Rxy = 0.0
        Ryy = 0.0
        Ry = 0.0
        Ix = 0.0
        Ixx = 0.0
        Ixy = 0.0
        Iyy = 0.0
        Iy = 0.0

        for j in range(period):
            jMinusOne = j + 1
            if np.isnan(source[i - jMinusOne]):
                X = 0
            else:
                X = source[i - jMinusOne]
            temp = PIx2 * jMinusOne / period
            Yc = np.cos(temp)
            Ys = -np.sin(temp)
            Rx = Rx + X
            Ix = Ix + X
            Rxx = Rxx + X * X
            Ixx = Ixx + X * X
            Rxy = Rxy + X * Yc
            Ixy = Ixy + X * Ys
            Ryy = Ryy + Yc * Yc
            Iyy = Iyy + Ys * Ys
            Ry = Ry + Yc
            Iy = Iy + Ys

        temp_1 = period * Rxx - Rx * Rx
        temp_2 = period * Ryy - Ry * Ry
        if temp_1 > 0.0 and temp_2 > 0.0:
            realPart[i] = (period * Rxy - Rx * Ry) / np.sqrt(temp_1 * temp_2)

        temp_1 = period * Ixx - Ix * Ix
        temp_2 = period * Iyy - Iy * Iy
        if temp_1 > 0.0 and temp_2 > 0.0:
            imagPart[i] = (period * Ixy - Ix * Iy) / np.sqrt(temp_1 * temp_2)

    # Correlation Angle Phasor
    HALF_OF_PI = np.arcsin(1.0)
    angle = np.where(imagPart == 0, 0.0, np.degrees(np.arctan(realPart / imagPart) + HALF_OF_PI))
    angle = np.where(imagPart > 0.0, angle - 180.0, angle)

    return realPart, imagPart, angle
