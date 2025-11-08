"""
Indicator Manager
Manages calculation and caching of technical indicators across multiple timeframes
"""

import numpy as np
from typing import Dict, Any, Optional
from jesse.indicators import (
    rsi, macd, bollinger_bands, stoch, atr,
    sma, ema, heikin_ashi_candles
)


class IndicatorManager:
    """
    Manages technical indicators for the strategy
    """

    def __init__(self):
        """Initialize indicator manager"""
        self.cache = {}

    def calculate_rsi(self, candles: np.ndarray, period: int = 14) -> float:
        """
        Calculate RSI for given candles

        Args:
            candles: numpy array with candle data
            period: RSI period

        Returns:
            float: RSI value
        """
        if len(candles) < period + 1:
            return 50.0  # Neutral value

        return rsi(candles, period=period)

    def calculate_macd(self, candles: np.ndarray,
                      fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
        """
        Calculate MACD for given candles

        Args:
            candles: numpy array with candle data
            fast: fast period
            slow: slow period
            signal: signal period

        Returns:
            dict with macd, signal, and histogram values
        """
        if len(candles) < slow + signal:
            return {'macd': 0.0, 'signal': 0.0, 'histogram': 0.0}

        result = macd(candles, fast_period=fast, slow_period=slow, signal_period=signal)

        return {
            'macd': float(result.macd),
            'signal': float(result.signal),
            'histogram': float(result.hist)
        }

    def calculate_bollinger_bands(self, candles: np.ndarray,
                                  period: int = 20, std: float = 2.0) -> Dict[str, float]:
        """
        Calculate Bollinger Bands for given candles

        Args:
            candles: numpy array with candle data
            period: BB period
            std: standard deviation multiplier

        Returns:
            dict with upper, middle, lower bands and position
        """
        if len(candles) < period:
            current_price = candles[-1][2] if len(candles) > 0 else 0.0
            return {
                'upper': current_price,
                'middle': current_price,
                'lower': current_price,
                'position': 0.5,  # Neutral
                'width': 0.0
            }

        bb = bollinger_bands(candles, period=period, devup=std, devdn=std)

        upper = float(bb.upperband)
        middle = float(bb.middleband)
        lower = float(bb.lowerband)
        current_price = candles[-1][2]

        # Calculate position within bands (0 = lower, 0.5 = middle, 1 = upper)
        if upper != lower:
            position = (current_price - lower) / (upper - lower)
        else:
            position = 0.5

        # Calculate band width (normalized by middle band)
        if middle != 0:
            width = (upper - lower) / middle
        else:
            width = 0.0

        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'position': position,
            'width': width
        }

    def calculate_stochastic(self, candles: np.ndarray,
                            k_period: int = 14, d_period: int = 3) -> Dict[str, float]:
        """
        Calculate Stochastic Oscillator for given candles

        Args:
            candles: numpy array with candle data
            k_period: K period
            d_period: D period

        Returns:
            dict with %K and %D values
        """
        if len(candles) < k_period + d_period:
            return {'k': 50.0, 'd': 50.0}

        result = stoch(candles, fastk_period=k_period, slowk_period=d_period, slowd_period=d_period)

        return {
            'k': float(result.k),
            'd': float(result.d)
        }

    def calculate_atr(self, candles: np.ndarray, period: int = 14) -> float:
        """
        Calculate Average True Range for given candles

        Args:
            candles: numpy array with candle data
            period: ATR period

        Returns:
            float: ATR value
        """
        if len(candles) < period + 1:
            return 0.0

        return float(atr(candles, period=period))

    def calculate_heikin_ashi(self, candles: np.ndarray) -> Dict[str, Any]:
        """
        Calculate Heikin Ashi candles and analyze trend

        Args:
            candles: numpy array with candle data

        Returns:
            dict with HA color, body size, and trend strength
        """
        if len(candles) < 2:
            return {
                'color': 'neutral',
                'body_size': 0.0,
                'trend_strength': 0.0
            }

        ha = heikin_ashi_candles(candles)

        ha_open = float(ha.open)
        ha_close = float(ha.close)
        ha_high = float(ha.high)
        ha_low = float(ha.low)

        # Determine color
        if ha_close > ha_open:
            color = 'green'
            trend_direction = 1.0
        elif ha_close < ha_open:
            color = 'red'
            trend_direction = -1.0
        else:
            color = 'neutral'
            trend_direction = 0.0

        # Calculate body size relative to total range
        total_range = ha_high - ha_low
        body_size = abs(ha_close - ha_open)

        if total_range > 0:
            body_ratio = body_size / total_range
        else:
            body_ratio = 0.0

        # Trend strength combines direction and body ratio
        trend_strength = trend_direction * body_ratio

        return {
            'color': color,
            'body_size': body_size,
            'body_ratio': body_ratio,
            'trend_strength': trend_strength,
            'high': ha_high,
            'low': ha_low,
            'open': ha_open,
            'close': ha_close
        }

    def calculate_all_indicators(self, candles: np.ndarray,
                                timeframe: str,
                                params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Calculate all indicators for given candles

        Args:
            candles: numpy array with candle data
            timeframe: timeframe identifier
            params: optional parameters for indicators

        Returns:
            dict with all indicator values
        """
        if params is None:
            params = {}

        # Get parameters with defaults
        rsi_period = params.get('rsi_period', 14)
        macd_fast = params.get('macd_fast', 12)
        macd_slow = params.get('macd_slow', 26)
        macd_signal = params.get('macd_signal', 9)
        bb_period = params.get('bb_period', 20)
        bb_std = params.get('bb_std', 2.0)
        stoch_k = params.get('stoch_k', 14)
        stoch_d = params.get('stoch_d', 3)
        atr_period = params.get('atr_period', 14)

        return {
            'timeframe': timeframe,
            'rsi': self.calculate_rsi(candles, rsi_period),
            'macd': self.calculate_macd(candles, macd_fast, macd_slow, macd_signal),
            'bb': self.calculate_bollinger_bands(candles, bb_period, bb_std),
            'stoch': self.calculate_stochastic(candles, stoch_k, stoch_d),
            'atr': self.calculate_atr(candles, atr_period),
            'ha': self.calculate_heikin_ashi(candles)
        }

    def get_indicator_features(self, indicators: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract numeric features from indicator data for ML/GA

        Args:
            indicators: dict of calculated indicators

        Returns:
            dict of numeric features
        """
        features = {}

        # RSI features
        rsi_value = indicators.get('rsi', 50.0)
        features['rsi'] = rsi_value
        features['rsi_overbought'] = 1.0 if rsi_value > 70 else 0.0
        features['rsi_oversold'] = 1.0 if rsi_value < 30 else 0.0

        # MACD features
        macd_data = indicators.get('macd', {})
        features['macd'] = macd_data.get('macd', 0.0)
        features['macd_signal'] = macd_data.get('signal', 0.0)
        features['macd_histogram'] = macd_data.get('histogram', 0.0)
        features['macd_bullish'] = 1.0 if macd_data.get('histogram', 0.0) > 0 else 0.0

        # Bollinger Bands features
        bb_data = indicators.get('bb', {})
        features['bb_position'] = bb_data.get('position', 0.5)
        features['bb_width'] = bb_data.get('width', 0.0)
        features['bb_upper_touch'] = 1.0 if bb_data.get('position', 0.5) > 0.95 else 0.0
        features['bb_lower_touch'] = 1.0 if bb_data.get('position', 0.5) < 0.05 else 0.0

        # Stochastic features
        stoch_data = indicators.get('stoch', {})
        features['stoch_k'] = stoch_data.get('k', 50.0)
        features['stoch_d'] = stoch_data.get('d', 50.0)
        features['stoch_overbought'] = 1.0 if stoch_data.get('k', 50.0) > 80 else 0.0
        features['stoch_oversold'] = 1.0 if stoch_data.get('k', 50.0) < 20 else 0.0

        # ATR features (volatility)
        features['atr'] = indicators.get('atr', 0.0)

        # Heikin Ashi features
        ha_data = indicators.get('ha', {})
        features['ha_trend_strength'] = ha_data.get('trend_strength', 0.0)
        features['ha_body_ratio'] = ha_data.get('body_ratio', 0.0)
        features['ha_bullish'] = 1.0 if ha_data.get('color', 'neutral') == 'green' else 0.0
        features['ha_bearish'] = 1.0 if ha_data.get('color', 'neutral') == 'red' else 0.0

        return features
