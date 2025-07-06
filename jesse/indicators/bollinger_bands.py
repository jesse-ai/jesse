from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad

# Try to import the high-performance Rust implementation
try:
    from jesse_rust import bollinger_bands as bb_rust  # type: ignore
    from jesse_rust import moving_std
except ImportError:  # pragma: no cover
    bb_rust = None  # type: ignore
    from jesse_rust import moving_std


BollingerBands = namedtuple('BollingerBands', ['upperband', 'middleband', 'lowerband'])


def _bollinger_bands_fallback(source: np.ndarray, period: int, devup: float, devdn: float, matype: int, devtype: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fallback implementation for non-SMA cases or when Rust is unavailable."""
    if devtype == 0:
        dev = moving_std(source, period)
    elif devtype == 1:
        dev = mean_ad(source, period, sequential=True)
    elif devtype == 2:
        dev = median_ad(source, period, sequential=True)
    else:
        raise ValueError("devtype not in (0, 1, 2)")

    middlebands = ma(source, period=period, matype=matype, sequential=True)
    upperbands = middlebands + devup * dev
    lowerbands = middlebands - devdn * dev
    
    return upperbands, middlebands, lowerbands


def bollinger_bands(
        candles: np.ndarray,
        period: int = 20,
        devup: float = 2,
        devdn: float = 2,
        matype: int = 0,
        devtype: int = 0,
        source_type: str = "close",
        sequential: bool = False
) -> BollingerBands:
    """
    BBANDS - Bollinger Bands

    :param candles: np.ndarray
    :param period: int - default: 20
    :param devup: float - default: 2
    :param devdn: float - default: 2
    :param matype: int - default: 0
    :param devtype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: BollingerBands(upperband, middleband, lowerband)
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    # Use optimized Rust implementation for standard case (SMA + standard deviation)
    if bb_rust is not None and matype == 0 and devtype == 0:
        upperbands, middlebands, lowerbands = bb_rust(source.astype(np.float64), period, devup, devdn)
    else:
        # Handle special cases or fallback
        if matype == 24 or matype == 29:
            # VWMA or VWAP need the full candles array
            upperbands, middlebands, lowerbands = _bollinger_bands_fallback(candles, period, devup, devdn, matype, devtype)
        else:
            upperbands, middlebands, lowerbands = _bollinger_bands_fallback(source, period, devup, devdn, matype, devtype)

    if sequential:
        return BollingerBands(upperbands, middlebands, lowerbands)
    else:
        return BollingerBands(upperbands[-1], middlebands[-1], lowerbands[-1])
