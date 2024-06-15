from collections import namedtuple

from .bollinger_bands import bollinger_bands
from .sma import sma
from .trange import trange

import numpy as np

TTMSqueezeTuple = namedtuple('TTMSqueezeTuple', ['sqz_signal'])


def TTMSqueeze(candles: np.ndarray, length_ttms: int = 20, bb_mult_ttms: float = 2.0, kc_mult_low_ttms: float = 2.0, source_type: str = "close") -> TTMSqueezeTuple:
    """
    @author daviddtech
    credits: https://www.tradingview.com/script/Mh3EmxF5-TTM-Squeeze-DaviddTech/

    TTMSQUEEZE - TTMSqueeze

    :param candles: np.ndarray
    :param length_ttms: int - default: 20
    :param bb_mult_ttms: float - default: 2.0
    :param kc_mult_low_ttms: float - default: 2.0
    :param source_type: str - default: "close"

    :return: TTMSqueezeTuple(sqz_signal)
    """
    bb_data = bollinger_bands(candles, length_ttms, bb_mult_ttms)

    kc_basis_ttms = sma(candles, length_ttms)
    devkc_ttms = sma(trange(candles, sequential=True), period=length_ttms)

    NoSqz_ttms = bb_data.lowerband < kc_basis_ttms - devkc_ttms * \
        kc_mult_low_ttms or bb_data.upperband > kc_basis_ttms + devkc_ttms * kc_mult_low_ttms

    sqz_signal = False
    if NoSqz_ttms:
        sqz_signal = True

    return TTMSqueezeTuple(sqz_signal)
