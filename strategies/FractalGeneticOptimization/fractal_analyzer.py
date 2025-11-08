"""
Fractal Candle Relationship Analyzer
Analyzes the relationship between consecutive candles across multiple timeframes
"""

import numpy as np
from typing import Dict, Tuple
from enum import IntEnum


class CandleState(IntEnum):
    """
    Four fundamental states of candle relationship:
    HHHL - Rising Power: High > Prev_High AND Low > Prev_Low
    HLLH - Falling Power: High < Prev_High AND Low < Prev_Low
    INSIDE - Indecision/Contraction: High < Prev_High AND Low > Prev_Low
    OUTSIDE - Volatility/Expansion: High > Prev_High AND Low < Prev_Low
    """
    HHHL = 1  # Rising Power (Bullish)
    HLLH = 2  # Falling Power (Bearish)
    INSIDE = 3  # Inside Bar (Consolidation)
    OUTSIDE = 4  # Outside Bar (Breakout/Volatility)


class FractalAnalyzer:
    """
    Analyzes fractal patterns across multiple timeframes
    """

    # All supported timeframes from largest to smallest
    TIMEFRAMES = [
        '3M',  # 3 months (Quarterly)
        '1M',  # 1 month (Monthly)
        '1W',  # 1 week (Weekly)
        '1D',  # 1 day (Daily)
        '12h', '8h', '4h', '2h', '1h',  # Hours
        '30m', '15m', '10m', '5m'  # Minutes
    ]

    @staticmethod
    def get_candle_state(candles: np.ndarray) -> CandleState:
        """
        Determines the current candle state by comparing with previous candle

        Args:
            candles: numpy array with shape (n, 6) containing [timestamp, open, close, high, low, volume]
                    Last two candles will be used for comparison

        Returns:
            CandleState enum value
        """
        if len(candles) < 2:
            return CandleState.INSIDE  # Default to neutral state

        # Current and previous candles
        current = candles[-1]
        previous = candles[-2]

        current_high = current[3]
        current_low = current[4]
        prev_high = previous[3]
        prev_low = previous[4]

        # Determine the state based on high/low relationship
        high_higher = current_high > prev_high
        low_higher = current_low > prev_low

        if high_higher and low_higher:
            return CandleState.HHHL  # Rising Power
        elif not high_higher and not low_higher:
            return CandleState.HLLH  # Falling Power
        elif not high_higher and low_higher:
            return CandleState.INSIDE  # Inside Bar
        else:  # high_higher and not low_higher
            return CandleState.OUTSIDE  # Outside Bar

    @staticmethod
    def get_candle_state_strength(candles: np.ndarray) -> float:
        """
        Calculates the strength of the current candle state
        Returns a value between 0 and 1

        Args:
            candles: numpy array with candle data

        Returns:
            float: strength value (0-1)
        """
        if len(candles) < 2:
            return 0.5

        current = candles[-1]
        previous = candles[-2]

        current_high = current[3]
        current_low = current[4]
        current_range = current_high - current_low

        prev_high = previous[3]
        prev_low = previous[4]
        prev_range = prev_high - prev_low

        if prev_range == 0:
            return 0.5

        # Calculate how much the candle has moved relative to previous
        high_diff = abs(current_high - prev_high) / prev_range
        low_diff = abs(current_low - prev_low) / prev_range

        # Average movement strength
        strength = (high_diff + low_diff) / 2.0

        # Normalize to 0-1 range
        return min(1.0, strength)

    @staticmethod
    def analyze_timeframe_trend(candles: np.ndarray, lookback: int = 5) -> Dict[str, float]:
        """
        Analyzes the trend of a timeframe by looking at multiple candles

        Args:
            candles: numpy array with candle data
            lookback: number of candles to analyze

        Returns:
            dict with trend analysis metrics
        """
        if len(candles) < lookback + 1:
            lookback = len(candles) - 1

        if lookback < 1:
            return {
                'bullish_score': 0.5,
                'bearish_score': 0.5,
                'volatility_score': 0.5,
                'trend_strength': 0.0
            }

        recent_candles = candles[-lookback-1:]

        bullish_count = 0
        bearish_count = 0
        inside_count = 0
        outside_count = 0

        # Analyze each candle pair
        for i in range(1, len(recent_candles)):
            state = FractalAnalyzer.get_candle_state(recent_candles[:i+1])

            if state == CandleState.HHHL:
                bullish_count += 1
            elif state == CandleState.HLLH:
                bearish_count += 1
            elif state == CandleState.INSIDE:
                inside_count += 1
            elif state == CandleState.OUTSIDE:
                outside_count += 1

        total = bullish_count + bearish_count + inside_count + outside_count
        if total == 0:
            total = 1

        bullish_score = bullish_count / total
        bearish_score = bearish_count / total
        volatility_score = outside_count / total
        consolidation_score = inside_count / total

        # Trend strength is the difference between bullish and bearish
        trend_strength = abs(bullish_score - bearish_score)

        return {
            'bullish_score': bullish_score,
            'bearish_score': bearish_score,
            'volatility_score': volatility_score,
            'consolidation_score': consolidation_score,
            'trend_strength': trend_strength
        }

    @staticmethod
    def get_multi_timeframe_alignment(states: Dict[str, CandleState]) -> float:
        """
        Calculates alignment score across multiple timeframes
        Higher score means more timeframes agree on direction

        Args:
            states: dict of {timeframe: CandleState}

        Returns:
            float: alignment score (-1 to 1), positive for bullish, negative for bearish
        """
        if not states:
            return 0.0

        bullish_weight = 0.0
        bearish_weight = 0.0
        total_weight = 0.0

        # Assign weights based on timeframe importance (larger = more weight)
        timeframe_weights = {
            '3M': 13, '1M': 12, '1W': 11, '1D': 10,
            '12h': 9, '8h': 8, '4h': 7, '2h': 6, '1h': 5,
            '30m': 4, '15m': 3, '10m': 2, '5m': 1
        }

        for tf, state in states.items():
            weight = timeframe_weights.get(tf, 1)
            total_weight += weight

            if state == CandleState.HHHL:
                bullish_weight += weight
            elif state == CandleState.HLLH:
                bearish_weight += weight
            elif state == CandleState.OUTSIDE:
                # Outside bars add to current trend
                # We'll consider them neutral for now
                pass

        if total_weight == 0:
            return 0.0

        # Calculate alignment score
        net_score = (bullish_weight - bearish_weight) / total_weight

        return net_score
