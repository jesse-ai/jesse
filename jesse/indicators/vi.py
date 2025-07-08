from collections import namedtuple

import numpy as np
from jesse.helpers import slice_candles

VI = namedtuple('VI', ['plus', 'minus'])


def vi(candles: np.ndarray, period: int = 14, sequential: bool = False) -> VI:
    """
    Vortex Indicator (VI)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: VI(plus, minus)
    """
    # Check if jesse_rust is available
    try:
        import jesse_rust
        
        candles = slice_candles(candles, sequential)
        
        # Use the Rust implementation
        vi_plus, vi_minus = jesse_rust.vi(candles, period, sequential)
        
        if sequential:
            return VI(vi_plus, vi_minus)
        else:
            return VI(vi_plus[-1], vi_minus[-1])
            
    except ImportError:
        # Fallback to pure Python implementation
        candles = slice_candles(candles, sequential)
        
        vpn_with_nan, vmn_with_nan = vi_fast_python(candles, period)

        if sequential:
            return VI(vpn_with_nan, vmn_with_nan)
        else:
            return VI(vpn_with_nan[-1], vmn_with_nan[-1])


def vi_fast_python(candles, period):
    """
    Pure Python implementation of VI calculation
    """
    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]
    n = len(candles_high)

    tr = np.zeros(n)
    vp = np.zeros(n)
    vm = np.zeros(n)
    
    tr[0] = candles_high[0] - candles_low[0]
    
    for i in range(1, n):
        hl = candles_high[i] - candles_low[i]
        hpc = np.abs(candles_high[i] - candles_close[i - 1])
        lpc = np.abs(candles_low[i] - candles_close[i - 1])
        tr[i] = np.amax(np.array([hl, hpc, lpc]))
        vp[i] = np.abs(candles_high[i] - candles_low[i - 1])
        vm[i] = np.abs(candles_low[i] - candles_high[i - 1])
    
    trd = np.zeros(n)
    vpd = np.zeros(n)
    vmd = np.zeros(n)
    
    for j in range(n - period + 1):
        trd[period - 1 + j] = np.sum(tr[j:j + period])
        vpd[period - 1 + j] = np.sum(vp[j:j + period])
        vmd[period - 1 + j] = np.sum(vm[j:j + period])
    
    trd = trd[period - 1:]
    vpd = vpd[period - 1:]
    vmd = vmd[period - 1:]
    
    vpn = vpd / trd
    vmn = vmd / trd
    
    vpn_with_nan = np.concatenate((np.full((candles.shape[0] - vpn.shape[0]), np.nan), vpn))
    vmn_with_nan = np.concatenate((np.full((candles.shape[0] - vmn.shape[0]), np.nan), vmn))
    
    return vpn_with_nan, vmn_with_nan
