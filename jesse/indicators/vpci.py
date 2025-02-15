from collections import namedtuple

from jesse.indicators.sma import sma
import numpy as np

from jesse.helpers import slice_candles

VPCI = namedtuple('VPCI', ['vpci', 'vpcis'])


def vpci(candles: np.ndarray, short_range: int = 5, long_range: int = 25, sequential: bool = False) -> VPCI:
    """
    VPCI - Volume Price Confirmation Indicator

    :param candles: np.ndarray
    :param short_range: int - default: 5
    :param long_range: int - default: 25
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    vwma_long = sma(candles[:, 2] * candles[:, 5], long_range, sequential=True) / sma(candles[:, 5], long_range, sequential=True)
    VPC = vwma_long - sma(candles[:, 2], long_range, sequential=True)

    vwma_short = sma(candles[:, 2] * candles[:, 5], short_range, sequential=True) / sma(candles[:, 5], short_range, sequential=True)
    VPR = vwma_short / sma(candles[:, 2], short_range, sequential=True)

    VM = sma(candles[:, 5], short_range, sequential=True) / sma(candles[:, 5], long_range, sequential=True)
    VPCI_val = VPC * VPR * VM

    VPCIS = sma(VPCI_val * candles[:, 5], short_range, sequential=True) / sma(candles[:, 5], short_range, sequential=True)

    if sequential:
        return VPCI(VPCI_val, VPCIS)
    else:
        return VPCI(VPCI_val[-1], VPCIS[-1])
