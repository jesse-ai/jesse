import numpy as np
import talib
from typing import Union

from jesse.helpers import get_candle_source, slice_candles, np_shift


def linreg(source, length, offset) -> np.ndarray:
    """Linear regression curve. A line that best fits the prices 
    specified over a user-defined time period. It is calculated 
    using the least squares method. The result of this function 
    is calculated using the formula: 
    
    linreg = intercept + slope * (length - 1 - offset), 
    where intercept and slope are the values calculated 
    with the least squares method on source series.
    
    na values in the source series are included in calculations and will produce an na result.
    
    Linear regression curve.
    
    """
    
    # Calculate intercept and slope using least squares method on source series
    slope = talib.LINEARREG_SLOPE(source, length)
    intercept = talib.LINEARREG_INTERCEPT(source, length)
    
    try:
        return intercept + slope * (length - 1 - offset)
    except Exception as e:
        return np.nan


def _rate(condition, top_wick, bottom_wick, body):
    
    # Where the condition is true, the body is multiplied by 2 otherwise it's 0
    body_multiplier = np.where(condition, 2 * body, 0)
    
    # Numerator represents the sum of top wick, bottom wick, and body_multiplier
    numerator = 0.5 * (top_wick + bottom_wick + body_multiplier)
    
    denominator = (top_wick + bottom_wick + body)
    
    ret = numerator / denominator
    
    return np.where(np.isnan(ret), 0.5, ret)

def _get_trend(len, volume, open, close, top_wick, bottom_wick, body):


    # Calculate deltaup/deltadown using boolean array operations
    deltaup = volume * _rate(open <= close, top_wick, bottom_wick, body)
    deltadown = volume * _rate(open > close, top_wick, bottom_wick, body)
    
    slope_volume_up = linreg(deltaup, len, 0) - linreg(deltaup, len, 1)
    slope_volume_down = linreg(deltadown, len, 0) - linreg(deltadown, len, 1)
    return (slope_volume_up, slope_volume_down)

def color_for_slope_and_intensity(slope: np.ndarray, intensity: np.ndarray, pos_map: dict, neg_map: dict) -> np.ndarray:

    # Initialize output array with zeros
    colors = np.zeros_like(slope, dtype=object)
    
    # For positive slopes
    pos_mask = slope > 0
    colors[pos_mask] = np.array([pos_map.get(int(i), '#000000') for i in intensity[pos_mask]])
    
    # For zero or negative slopes
    neg_mask = ~pos_mask
    colors[neg_mask] = np.array([neg_map.get(int(i), '#000000') for i in intensity[neg_mask]])
    
    return colors[-1] if isinstance(colors, np.ndarray) and len(colors) > 0 else '#000000'

def vslrt(
    candles: np.ndarray,
    short_length: int = 20,
    long_length: int = 50,
    source_type: str = "close",
    sequential: bool = False
) -> Union[tuple, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:

    if sequential:
        raise ValueError("Error: sequential not supported")
    else:
        candles = slice_candles(candles, False)

    if short_length < 5 or long_length < 5:
        raise ValueError("Error: short_length and long_length must be at least 5")

    # Extract candle data directly from the candles array
    # Candles array has columns: timestamp, open, close, high, low, volume
    open = candles[:, 1]
    close = candles[:, 2]
    high = candles[:, 3]
    low = candles[:, 4]
    volume = candles[:, 5]

    # Get source data
    if source_type == "close":
        src = close
    elif source_type == "open":
        src = open
    elif source_type == "high":
        src = high
    elif source_type == "low":
        src = low
    else:
        raise ValueError(f"Invalid source_type: {source_type}")
    
    # Get short/long-term regression slope
    slope_price = linreg(src, short_length, 0) - linreg(src, short_length, 1)
    slope_price_lt = linreg(src, long_length, 0) - linreg(src, long_length, 1)
    
    # Get the size of top/bottom/body of the candles
    top_wick = high - np.maximum(open, close)
    bottom_wick = np.minimum(open, close) - low
    body = np.abs(close - open)
    
    # Get buy/sell volume regression slopes for short term period
    slope_volume_up_short, slope_volume_down_short = _get_trend(short_length, volume, open, close, top_wick, bottom_wick, body)
    
    # Calculate short-term intensity using numpy operations
    intensity_short = np.zeros_like(slope_price)
    
    # Bullish conditions
    bull_mask = slope_price > 0
    bull_strong = (slope_volume_up_short > 0) & (slope_volume_up_short > slope_volume_down_short)
    bull_medium = (slope_volume_up_short > 0) & ~bull_strong
    
    intensity_short = np.where(bull_mask & bull_strong, 3, intensity_short)
    intensity_short = np.where(bull_mask & bull_medium, 2, intensity_short)
    intensity_short = np.where(bull_mask & ~bull_strong & ~bull_medium, 1, intensity_short)
    
    # Bearish conditions
    bear_mask = slope_price <= 0
    bear_strong = (slope_volume_down_short > 0) & (slope_volume_up_short < slope_volume_down_short)
    bear_medium = (slope_volume_down_short > 0) & ~bear_strong
    
    intensity_short = np.where(bear_mask & bear_strong, -3, intensity_short)
    intensity_short = np.where(bear_mask & bear_medium, -2, intensity_short)
    intensity_short = np.where(bear_mask & ~bear_strong & ~bear_medium, -1, intensity_short)
    
    # Get long-term trends
    slope_volume_up_long, slope_volume_down_long = _get_trend(
        long_length, volume, open, close, top_wick, bottom_wick, body
    )
    
    # Calculate long-term intensity using numpy operations
    intensity_long = np.zeros_like(slope_price_lt)
    
    # Bullish conditions
    bull_mask_lt = slope_price_lt > 0
    bull_strong_lt = (slope_volume_up_long > 0) & (slope_volume_up_long > slope_volume_down_long)
    bull_medium_lt = (slope_volume_up_long > 0) & ~bull_strong_lt
    
    intensity_long = np.where(bull_mask_lt & bull_strong_lt, 3, intensity_long)
    intensity_long = np.where(bull_mask_lt & bull_medium_lt, 2, intensity_long)
    intensity_long = np.where(bull_mask_lt & ~bull_strong_lt & ~bull_medium_lt, 1, intensity_long)
    
    # Bearish conditions
    bear_mask_lt = slope_price_lt <= 0
    bear_strong_lt = (slope_volume_down_long > 0) & (slope_volume_up_long < slope_volume_down_long)
    bear_medium_lt = (slope_volume_down_long > 0) & ~bear_strong_lt
    
    intensity_long = np.where(bear_mask_lt & bear_strong_lt, -3, intensity_long)
    intensity_long = np.where(bear_mask_lt & bear_medium_lt, -2, intensity_long)
    intensity_long = np.where(bear_mask_lt & ~bear_strong_lt & ~bear_medium_lt, -1, intensity_long)
    
    if not sequential:
        return slope_price[-1] * short_length, slope_price_lt[-1] * long_length, intensity_short[-1], intensity_long[-1]
    else:
        return slope_price * short_length, slope_price_lt * long_length, intensity_short, intensity_long





