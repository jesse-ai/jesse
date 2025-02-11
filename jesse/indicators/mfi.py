from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def mfi(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    MFI - Money Flow Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # Extract high, low, close and volume from candles array
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    volume = candles[:, 5]

    # Compute Typical Price for each candle
    typical_prices = (high + low + close) / 3.0

    # Compute Raw Money Flow = Typical Price * Volume
    raw_mf = typical_prices * volume

    # Initialize positive and negative flows
    pos_flow = np.zeros_like(typical_prices)
    neg_flow = np.zeros_like(typical_prices)
    # For each candle (starting from 1) decide if it's positive or negative money flow
    pos_flow[1:] = np.where(typical_prices[1:] > typical_prices[:-1], raw_mf[1:], 0)
    neg_flow[1:] = np.where(typical_prices[1:] < typical_prices[:-1], raw_mf[1:], 0)

    # Compute rolling sums over the specified period using convolution
    roll_pos = np.convolve(pos_flow, np.ones(period), mode='valid')
    roll_neg = np.convolve(neg_flow, np.ones(period), mode='valid')

    # Compute Money Flow Ratio; handle division by zero by treating as infinity
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.divide(roll_pos, roll_neg, out=np.full_like(roll_pos, np.inf, dtype=float), where=roll_neg != 0)

    # Compute MFI
    mfi_values = 100 - (100 / (1 + ratio))

    # Prepend NaNs for indices that couldn't compute a full period
    pad = np.full(period - 1, np.nan)
    mfi_values = np.concatenate((pad, mfi_values))

    return mfi_values if sequential else mfi_values[-1]
