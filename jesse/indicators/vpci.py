import numpy as np
import tulipy as ti
import talib

from collections import namedtuple

VPCI = namedtuple('VPCI', ['vpci', 'vpcis', 'lower', 'mid', 'upper'])


def vpci(candles: np.ndarray, short_range=5, long_range=25, bb_lenght=20, bb_mult=2, sequential=False) -> VPCI:
    """
    VPCI - Volume Price Confirmation Indicator

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    vwma_long = talib.SMA( candles[:, 2] * candles[:, 5], short_range) / talib.SMA(candles[:, 5], long_range)
    VPC = vwma_long - talib.SMA(candles[:, 2], long_range)

    vwma_short = talib.SMA( candles[:, 2] * candles[:, 5], short_range) / talib.SMA(candles[:, 5], short_range)
    VPR = vwma_short - talib.SMA(candles[:, 2], short_range)

    VM = talib.SMA(candles[:, 5], short_range) / talib.SMA(candles[:, 5], long_range)
    VPCI_val = VPC * VPR * VM

    VPCIS = talib.SMA( VPCI_val * candles[:, 5], short_range) / talib.SMA(candles[:, 5], short_range)

    basis = talib.SMA(VPCI_val, bb_lenght)
    dev = (bb_mult * talib.STDDEV(VPCI_val, bb_lenght))
    upper = (basis + dev)
    lower = (basis - dev)

    if sequential:
        return VPCI(VPCI_val, VPCIS, lower, basis, upper)
    else:
        return VPCI(VPCI_val[-1], VPCIS[-1], lower[-1], basis[-1], upper[-1])
