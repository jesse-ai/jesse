from typing import Union
import numpy as np
from jesse.helpers import get_candle_source, slice_candles


def vwap(
        candles: np.ndarray, source_type: str = "hlc3", anchor: str = "D", sequential: bool = False
) -> Union[float, np.ndarray]:
    """
    VWAP

    :param candles: np.ndarray
    :param source_type: str - default: "hlc3"
    :param anchor: str - default: "D"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    # Check if jesse_rust is available
    try:
        import jesse_rust
        
        candles = slice_candles(candles, sequential)
        
        # Use the Rust implementation with anchoring support
        result = jesse_rust.vwap(candles, source_type, anchor, sequential)
        
        if sequential:
            return result
        else:
            return None if np.isnan(result[-1]) else result[-1]
    
    except ImportError:
        # Fallback to original Python implementation with anchoring
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
        
        # Convert timestamps to period indices
        timestamps = candles[:, 0].astype('datetime64[ms]').astype(f'datetime64[{anchor}]')
        group_indices = np.zeros(len(timestamps), dtype=np.int64)
        
        # Mark the start of each new period
        group_indices[1:] = (timestamps[1:] != timestamps[:-1]).astype(np.int64)
        group_indices = np.cumsum(group_indices)
        
        vwap_values = _calculate_vwap(source, candles[:, 5], group_indices)

        if sequential:
            return vwap_values
        else:
            return None if np.isnan(vwap_values[-1]) else vwap_values[-1]


def _calculate_vwap(source: np.ndarray, volume: np.ndarray, group_indices: np.ndarray) -> np.ndarray:
    """
    Calculate VWAP values with anchoring logic (pure Python implementation fallback)
    """
    vwap_values = np.zeros_like(source)
    cum_vol = 0.0
    cum_vol_price = 0.0
    current_group = group_indices[0]
    
    for i in range(len(source)):
        if group_indices[i] != current_group:
            cum_vol = 0.0
            cum_vol_price = 0.0
            current_group = group_indices[i]
            
        vol_price = volume[i] * source[i]
        cum_vol_price += vol_price
        cum_vol += volume[i]
        
        vwap_values[i] = cum_vol_price / cum_vol if cum_vol != 0 else np.nan
        
    return vwap_values
