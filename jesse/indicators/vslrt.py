import numpy as np
import talib
from typing import Union

from jesse.helpers import slice_candles


def linreg(source: np.ndarray, length: int, offset: int) -> np.ndarray:
    """
    Calculates a simple "best fit" line (linear regression) over a specific number of data points.
    
    Linear regression is a way of finding the line that best fits a set of data points
    by minimizing the sum of the squares of the differences between the actual data
    and the predicted values on the line.

    This function uses TA-Lib's built-in LINEARREG_SLOPE and LINEARREG_INTERCEPT 
    to compute the slope and intercept of the best fit line. It then constructs the 
    final linear regression value for each point with the formula:
    
        linreg = intercept + slope * (length - 1 - offset)
    
    Parameters
    ----------
    source : np.ndarray
        The data to be used for linear regression (e.g., candle closes).
    length : int
        The number of data points to consider for the regression.
    offset : int
        How many steps to shift the fitted line (used to compare consecutive slopes).
    
    Returns
    -------
    np.ndarray
        An array representing the linear regression values for each data point.
        If the computation fails, NaN is returned for that data point.
    """
    # Calculate slope and intercept using the TA-Lib linear regression functions
    slope = talib.LINEARREG_SLOPE(source, length)
    intercept = talib.LINEARREG_INTERCEPT(source, length)
    
    try:
        return intercept + slope * (length - 1 - offset)
    except Exception:
        return np.nan


def _rate(condition: np.ndarray, top_wick: np.ndarray, bottom_wick: np.ndarray, body: np.ndarray) -> np.ndarray:
    """
    Assigns a weight (or 'rate') to candle segments based on whether a condition is met.
    
    This function is used to determine how much volume to allocate to the 'body' (the main
    part of the candle) compared to the wicks (the thin lines above and below the body).
    If 'condition' is True (e.g., a bullish candle), then the 'body' gets a higher weighting.
    
    Parameters
    ----------
    condition : np.ndarray
        Boolean array indicating which candles meet a specific requirement (e.g. close >= open).
    top_wick : np.ndarray
        The distance (price difference) of the top wick.
    bottom_wick : np.ndarray
        The distance (price difference) of the bottom wick.
    body : np.ndarray
        The distance (price difference) representing the candle body.
    
    Returns
    -------
    np.ndarray
        An array of weights for each candle, influencing how volume is calculated later.
    """
    # Multiply the body by 2 if condition is True, otherwise 0
    body_multiplier = np.where(condition, 2 * body, 0)
    
    # The numerator is half of (top wick + bottom wick + body_multiplier)
    numerator = 0.5 * (top_wick + bottom_wick + body_multiplier)
    
    # The denominator is the sum of the actual candle segments
    denominator = (top_wick + bottom_wick + body)
    
    # Avoid division by zero: if 'ret' is NaN, default to 0.5
    ret = numerator / denominator
    return np.where(np.isnan(ret), 0.5, ret)


def _get_trend(
    length: int,
    volume: np.ndarray,
    open: np.ndarray,
    close: np.ndarray,
    top_wick: np.ndarray,
    bottom_wick: np.ndarray,
    body: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """
    Determines the short-term change (slope) in 'bullish volume' vs 'bearish volume' 
    by using linear regression on volume allocations.
    
    This function calculates two arrays:
    - slope_volume_up: the slope of how bullish (buying) volume changes over time
    - slope_volume_down: the slope of how bearish (selling) volume changes over time
    
    Parameters
    ----------
    length : int
        The number of data points to consider for each linear regression segment.
    volume : np.ndarray
        The volume (number of shares/contracts traded) for each candle.
    open : np.ndarray
        The opening prices for each candle.
    close : np.ndarray
        The closing prices for each candle.
    top_wick : np.ndarray
        The distance of the top wick for each candle.
    bottom_wick : np.ndarray
        The distance of the bottom wick for each candle.
    body : np.ndarray
        The distance of the candle body for each candle.
    
    Returns
    -------
    (np.ndarray, np.ndarray)
        A tuple containing:
        - slope_volume_up: bullish volume trend over the specified length
        - slope_volume_down: bearish volume trend over the specified length
    """
    # Calculate the bullish portion of volume
    deltaup = volume * _rate(open <= close, top_wick, bottom_wick, body)
    
    # Calculate the bearish portion of volume
    deltadown = volume * _rate(open > close, top_wick, bottom_wick, body)
    
    # Measure how fast these bullish and bearish volumes are changing (the "slope" of volume)
    slope_volume_up = linreg(deltaup, length, 0) - linreg(deltaup, length, 1)
    slope_volume_down = linreg(deltadown, length, 0) - linreg(deltadown, length, 1)
    
    return (slope_volume_up, slope_volume_down)


def vslrt(
    candles: np.ndarray,
    short_length: int = 20,
    long_length: int = 50,
    source_type: str = "close",
    sequential: bool = False
) -> Union[tuple, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """
    Volume Slope Linear Regression Trend (VSLRT)

    This indicator tries to measure both price and volume trends (short-term and long-term)
    by comparing the slopes of linear regressions on price data and volume data. 
    It attempts to show not only the direction of the market (bullish or bearish)
    but also how strong that trend is, based on volume.

    Parameters
    ----------
    candles : np.ndarray
        A 2D array of candle data. Each row typically contains:
        [timestamp, open, close, high, low, volume].
    short_length : int, optional
        The number of data points to use for the short-term regression calculation, by default 20.
    long_length : int, optional
        The number of data points to use for the long-term regression calculation, by default 50.
    source_type : str, optional
        Which price to use as the data source ('close', 'open', 'high', or 'low'), by default "close".
    sequential : bool, optional
        If True, returns arrays for each data point instead of a single value.

    Returns
    -------
    tuple or tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        If sequential is False:
            (short_price_slope, long_price_slope, short_intensity, long_intensity)
            Each of these is a single value for the latest data point.
        
        If sequential is True:
            (all_short_price_slopes, all_long_price_slopes, all_short_intensities, all_long_intensities)
            Each is an array for the entire data series.
    
    Raises
    ------
    ValueError
        If short_length/long_length < 5, or if source_type is invalid.
    """
    # Slice the candles based on 'sequential' mode:
    #   - If sequential=False, usually returns the last few (or last) candles.
    #   - If sequential=True, returns the entire candle series.
    candles = slice_candles(candles, sequential=sequential)

    # Check for valid short/long lengths
    if short_length < 5 or long_length < 5:
        raise ValueError("Error: short_length and long_length must be at least 5")

    # Unpack the candle data:
    # candles = [timestamp, open, close, high, low, volume]
    open_price = candles[:, 1]
    close_price = candles[:, 2]
    high_price = candles[:, 3]
    low_price = candles[:, 4]
    volume = candles[:, 5]

    # Determine which price array to use for the price slope calculation
    if source_type == "close":
        src = close_price
    elif source_type == "open":
        src = open_price
    elif source_type == "high":
        src = high_price
    elif source_type == "low":
        src = low_price
    else:
        raise ValueError(f"Invalid source_type: {source_type}")
    
    # Calculate short-term price slope by comparing consecutive linear regressions
    slope_price_short = linreg(src, short_length, 0) - linreg(src, short_length, 1)
    
    # Calculate long-term price slope similarly
    slope_price_long = linreg(src, long_length, 0) - linreg(src, long_length, 1)
    
    # Calculate candle 'segments': top wick, bottom wick, and body
    top_wick = high_price - np.maximum(open_price, close_price)
    bottom_wick = np.minimum(open_price, close_price) - low_price
    body = np.abs(close_price - open_price)
    
    # Get bullish/bearish volume trends for the short term
    slope_volume_up_short, slope_volume_down_short = _get_trend(
        short_length, volume, open_price, close_price, top_wick, bottom_wick, body
    )
    
    # Assign short-term intensity based on price slope and volume slope
    intensity_short = np.zeros_like(slope_price_short)
    
    # For bullish scenarios (slope > 0)
    bull_mask_short = slope_price_short > 0
    bull_strong_short = (slope_volume_up_short > 0) & (slope_volume_up_short > slope_volume_down_short)
    bull_medium_short = (slope_volume_up_short > 0) & ~bull_strong_short

    intensity_short = np.where(bull_mask_short & bull_strong_short, 3, intensity_short)
    intensity_short = np.where(bull_mask_short & bull_medium_short, 2, intensity_short)
    intensity_short = np.where(bull_mask_short & ~bull_strong_short & ~bull_medium_short, 1, intensity_short)
    
    # For bearish scenarios (slope <= 0)
    bear_mask_short = slope_price_short <= 0
    bear_strong_short = (slope_volume_down_short > 0) & (slope_volume_up_short < slope_volume_down_short)
    bear_medium_short = (slope_volume_down_short > 0) & ~bear_strong_short

    intensity_short = np.where(bear_mask_short & bear_strong_short, -3, intensity_short)
    intensity_short = np.where(bear_mask_short & bear_medium_short, -2, intensity_short)
    intensity_short = np.where(bear_mask_short & ~bear_strong_short & ~bear_medium_short, -1, intensity_short)
    
    # Get bullish/bearish volume trends for the long term
    slope_volume_up_long, slope_volume_down_long = _get_trend(
        long_length, volume, open_price, close_price, top_wick, bottom_wick, body
    )
    
    # Assign long-term intensity based on price slope and volume slope
    intensity_long = np.zeros_like(slope_price_long)
    
    bull_mask_long = slope_price_long > 0
    bull_strong_long = (slope_volume_up_long > 0) & (slope_volume_up_long > slope_volume_down_long)
    bull_medium_long = (slope_volume_up_long > 0) & ~bull_strong_long
    
    intensity_long = np.where(bull_mask_long & bull_strong_long, 3, intensity_long)
    intensity_long = np.where(bull_mask_long & bull_medium_long, 2, intensity_long)
    intensity_long = np.where(bull_mask_long & ~bull_strong_long & ~bull_medium_long, 1, intensity_long)
    
    bear_mask_long = slope_price_long <= 0
    bear_strong_long = (slope_volume_down_long > 0) & (slope_volume_up_long < slope_volume_down_long)
    bear_medium_long = (slope_volume_down_long > 0) & ~bear_strong_long
    
    intensity_long = np.where(bear_mask_long & bear_strong_long, -3, intensity_long)
    intensity_long = np.where(bear_mask_long & bear_medium_long, -2, intensity_long)
    intensity_long = np.where(bear_mask_long & ~bear_strong_long & ~bear_medium_long, -1, intensity_long)
    
    # If sequential=False, return only the last data point for each metric
    if not sequential:
        return (
            slope_price_short[-1] * short_length,
            slope_price_long[-1] * long_length,
            intensity_short[-1],
            intensity_long[-1]
        )
    else:
        # If sequential=True, return arrays for the entire series
        return (
            slope_price_short * short_length,
            slope_price_long * long_length,
            intensity_short,
            intensity_long
        )