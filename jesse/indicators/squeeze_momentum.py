from collections import namedtuple

from .bollinger_bands import bollinger_bands
from .sma import sma
from .trange import trange
from .linearreg import linearreg
from .stddev import stddev
import numpy as np

SqueezeMomentum = namedtuple('SqueezeMomentum', ['squeeze', 'momentum', 'momentum_signal'])


def squeeze_momentum(candles: np.ndarray, length: int = 20, mult: float = 2.0, length_kc: int = 20, mult_kc: float = 1.5, sequential: bool = True) -> SqueezeMomentum:
    """
    @author lazyBear
    credits: https://www.tradingview.com/script/nqQ1DT5a-Squeeze-Momentum-Indicator-LazyBear/

    squeeze_momentum

    :param candles: np.ndarray
    :length: int - default: 20
    :mult: float - default: 2.0
    :length_kc: float - default: 2.0
    :mult_kc: float - default: 1.5
    :sequential: bool - default: True

    :return: SqueezeMomentum(squeeze, momentum, momentum_signal)
    """
    # calculate bollinger bands
    basis = sma(candles, length, sequential=True)
    dev = mult_kc * stddev(candles, length, sequential=True)
    upper_bb = basis + dev
    lower_bb = basis - dev

    # calculate KC
    ma = sma(candles, length_kc, sequential=True)
    range_ma = sma(trange(candles, sequential=True), period=length_kc, sequential=True)
    upper_kc = ma + range_ma * mult_kc
    lower_kc = ma - range_ma * mult_kc

    sqz = []
    for i in range(len(lower_bb)):
        sqz_on = (lower_bb[i] > lower_kc[i]) and (upper_bb[i] < upper_kc[i])
        sqz_off = (lower_bb[i] < lower_kc[i]) and (upper_bb[i] > upper_kc[i])
        noSqz = (sqz_on == False) and (sqz_off == False)
        sqz.append(0 if noSqz else (-1 if sqz_on else 1))

    highs = np.nan_to_num(_highest(candles[:, 3], length_kc), 0)
    lows = np.nan_to_num(_lowest(candles[:, 4], length_kc), 0)
    sma_arr = np.nan_to_num(sma(candles, period=length_kc, sequential=True))

    momentum = []
    for i in range(len(highs)):
        momentum.append(candles[:, 2][i] - ((highs[i] + lows[i]) / 2 + sma_arr[i]) / 2)

    momentum = linearreg(np.array(momentum), period=length_kc, sequential=True)

    momentum_signal = []
    for i in range(len(momentum) - 1):
        if momentum[i + 1] > 0:
            momentum_signal.append(1 if momentum[i + 1] > momentum[i] else 2)
        else:
            momentum_signal.append(-1 if momentum[i + 1] < momentum[i] else -2)

    if sequential:
        return SqueezeMomentum(sqz, momentum, momentum_signal)
    else:
        return SqueezeMomentum(sqz[-1], momentum[-1], momentum_signal[-1])


def _highest(values, length):
    # Ensure values is a NumPy array for efficient computation
    values = np.asarray(values)
    # Initialize an array to hold the highest values
    highest_values = np.full(values.shape, np.nan)
    # Compute the highest value for each window
    for i in range(length - 1, len(values)):
        highest_values[i] = np.max(values[i - length + 1:i + 1])
    return highest_values


def _lowest(values, length):
    # Ensure values is a NumPy array for efficient computation
    values = np.asarray(values)
    # Initialize an array to hold the lowest values
    lowest_values = np.full(values.shape, np.nan)
    # Compute the lowest value for each window
    for i in range(length - 1, len(values)):
        lowest_values[i] = np.min(values[i - length + 1:i + 1])
    return lowest_values
