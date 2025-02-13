from collections import namedtuple

from jesse.indicators.roc import roc as _roc
from jesse.indicators.sma import sma as _sma
import numpy as np

from jesse.helpers import get_candle_source, slice_candles

KST = namedtuple('KST', ['line', 'signal'])


def kst(candles: np.ndarray, sma_period1: int = 10, sma_period2: int = 10, sma_period3: int = 10, sma_period4: int = 15,
        roc_period1: int = 10, roc_period2: int = 15, roc_period3: int = 20, roc_period4: int = 30,
        signal_period: int = 9, source_type: str = "close", sequential: bool = False) -> KST:
    """
    Know Sure Thing (KST)

    :param candles: np.ndarray
    :param sma_period1: int - default: 10
    :param sma_period2: int - default: 10
    :param sma_period3: int - default: 10
    :param sma_period4: int - default: 15
    :param roc_period1: int - default: 10
    :param roc_period2: int - default: 15
    :param roc_period3: int - default: 20
    :param roc_period4: int - default: 30
    :param signal_period: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: KST(line, signal)
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    aroc1 = _sma(_roc(source, roc_period1, sequential=True), sma_period1, sequential=True)
    aroc2 = _sma(_roc(source, roc_period2, sequential=True), sma_period2, sequential=True)
    aroc3 = _sma(_roc(source, roc_period3, sequential=True), sma_period3, sequential=True)
    aroc4 = _sma(_roc(source, roc_period4, sequential=True), sma_period4, sequential=True)

    # Align arrays so that all have the same length as aroc4
    aligned_len = aroc4.size
    aroc1_aligned = aroc1[aroc1.size - aligned_len:]
    aroc2_aligned = aroc2[aroc2.size - aligned_len:]
    aroc3_aligned = aroc3[aroc3.size - aligned_len:]

    line = aroc1_aligned + 2 * aroc2_aligned + 3 * aroc3_aligned + 4 * aroc4
    signal = _sma(line, signal_period, sequential=True)

    if sequential:
        return KST(line, signal)
    else:
        return KST(line[-1], signal[-1])
