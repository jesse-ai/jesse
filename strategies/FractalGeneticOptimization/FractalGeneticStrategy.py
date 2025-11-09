"""
Fractal Genetic Optimization Strategy for Jesse Trading Framework

This strategy implements a sophisticated multi-timeframe fractal analysis approach
combined with classical technical indicators. It uses genetic algorithm optimization
to find the optimal weights for different timeframes and indicators.

Author: Claude AI Assistant
Framework: Jesse
Trading Timeframe: 5m (can be configured)
"""

from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from .fractal_analyzer import FractalAnalyzer, CandleState
from .indicator_manager import IndicatorManager


class FractalGeneticStrategy(Strategy):
    """
    Multi-Timeframe Fractal Strategy with Genetic Algorithm Optimization

    Core Philosophy:
    - Analyzes fractal candle relationships across multiple timeframes
    - Combines with classical technical indicators (RSI, MACD, BB, Stochastic, ATR, HA)
    - Uses weighted scoring system optimized via Genetic Algorithm
    - Implements dynamic stop-loss and take-profit based on ATR
    """

    def __init__(self):
        super().__init__()
        self.fractal_analyzer = FractalAnalyzer()
        self.indicator_manager = IndicatorManager()

        # Cache for candles to avoid repeated fetches
        self.candle_cache = {}

    def hyperparameters(self):
        """
        Define hyperparameters for genetic algorithm optimization
        These will be tuned by Jesse's genetic algorithm
        """
        return [
            # === Fractal State Weights ===
            # Weights for each timeframe's fractal state
            {'name': 'weight_3M', 'type': float, 'min': 0.0, 'max': 10.0, 'default': 5.0},
            {'name': 'weight_1M', 'type': float, 'min': 0.0, 'max': 10.0, 'default': 4.5},
            {'name': 'weight_1W', 'type': float, 'min': 0.0, 'max': 10.0, 'default': 4.0},
            {'name': 'weight_1D', 'type': float, 'min': 0.0, 'max': 10.0, 'default': 3.5},
            {'name': 'weight_12h', 'type': float, 'min': 0.0, 'max': 8.0, 'default': 3.0},
            {'name': 'weight_8h', 'type': float, 'min': 0.0, 'max': 8.0, 'default': 2.8},
            {'name': 'weight_4h', 'type': float, 'min': 0.0, 'max': 8.0, 'default': 2.5},
            {'name': 'weight_2h', 'type': float, 'min': 0.0, 'max': 6.0, 'default': 2.2},
            {'name': 'weight_1h', 'type': float, 'min': 0.0, 'max': 6.0, 'default': 2.0},
            {'name': 'weight_30m', 'type': float, 'min': 0.0, 'max': 4.0, 'default': 1.5},
            {'name': 'weight_15m', 'type': float, 'min': 0.0, 'max': 4.0, 'default': 1.2},
            {'name': 'weight_10m', 'type': float, 'min': 0.0, 'max': 4.0, 'default': 1.0},
            {'name': 'weight_5m', 'type': float, 'min': 0.0, 'max': 4.0, 'default': 0.8},

            # === Indicator Parameters ===
            {'name': 'rsi_period', 'type': int, 'min': 7, 'max': 21, 'default': 14},
            {'name': 'rsi_weight', 'type': float, 'min': 0.0, 'max': 5.0, 'default': 2.0},

            {'name': 'macd_fast', 'type': int, 'min': 8, 'max': 16, 'default': 12},
            {'name': 'macd_slow', 'type': int, 'min': 20, 'max': 32, 'default': 26},
            {'name': 'macd_signal', 'type': int, 'min': 7, 'max': 12, 'default': 9},
            {'name': 'macd_weight', 'type': float, 'min': 0.0, 'max': 5.0, 'default': 2.5},

            {'name': 'bb_period', 'type': int, 'min': 15, 'max': 25, 'default': 20},
            {'name': 'bb_std', 'type': float, 'min': 1.5, 'max': 3.0, 'default': 2.0},
            {'name': 'bb_weight', 'type': float, 'min': 0.0, 'max': 5.0, 'default': 1.5},

            {'name': 'stoch_k', 'type': int, 'min': 10, 'max': 21, 'default': 14},
            {'name': 'stoch_d', 'type': int, 'min': 2, 'max': 5, 'default': 3},
            {'name': 'stoch_weight', 'type': float, 'min': 0.0, 'max': 5.0, 'default': 1.5},

            {'name': 'atr_period', 'type': int, 'min': 10, 'max': 21, 'default': 14},
            {'name': 'atr_weight', 'type': float, 'min': 0.0, 'max': 3.0, 'default': 1.0},

            {'name': 'ha_weight', 'type': float, 'min': 0.0, 'max': 5.0, 'default': 2.0},

            # === Risk Management ===
            {'name': 'stop_loss_atr_multiplier', 'type': float, 'min': 1.0, 'max': 4.0, 'default': 2.0},
            {'name': 'take_profit_atr_multiplier', 'type': float, 'min': 1.5, 'max': 6.0, 'default': 3.0},
            {'name': 'risk_per_trade', 'type': float, 'min': 0.01, 'max': 0.05, 'default': 0.02},

            # === Signal Thresholds ===
            {'name': 'min_score_long', 'type': float, 'min': 0.3, 'max': 0.8, 'default': 0.5},
            {'name': 'min_score_short', 'type': float, 'min': 0.3, 'max': 0.8, 'default': 0.5},

            # === Trend Filter ===
            {'name': 'require_trend_alignment', 'type': bool, 'default': True},
            {'name': 'min_trend_strength', 'type': float, 'min': 0.1, 'max': 0.5, 'default': 0.2},
        ]

    def get_timeframe_candles(self, timeframe: str) -> Optional[np.ndarray]:
        """
        Fetch candles for a specific timeframe with caching

        Args:
            timeframe: timeframe string (e.g., '1h', '4h', '1D')

        Returns:
            numpy array with candle data or None if not available
        """
        try:
            # Use current route's exchange and symbol
            candles = self.get_candles(self.exchange, self.symbol, timeframe)
            return candles if len(candles) > 0 else None
        except Exception as e:
            # Timeframe might not be available in config
            return None

    def calculate_fractal_score(self) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate the fractal analysis score across all timeframes

        Returns:
            tuple of (score, debug_info)
            score: -1 (bearish) to +1 (bullish)
            debug_info: dict with analysis details
        """
        timeframes = self.fractal_analyzer.TIMEFRAMES
        states = {}
        weights_sum = 0.0
        weighted_score = 0.0

        debug_info = {
            'timeframe_states': {},
            'timeframe_scores': {}
        }

        for tf in timeframes:
            candles = self.get_timeframe_candles(tf)
            if candles is None or len(candles) < 2:
                continue

            # Get fractal state for this timeframe
            state = self.fractal_analyzer.get_candle_state(candles)
            states[tf] = state

            # Get weight for this timeframe from hyperparameters
            weight_key = f'weight_{tf}'
            weight = self.hp.get(weight_key, 1.0)

            # Convert state to score
            if state == CandleState.HHHL:
                state_score = 1.0  # Bullish
            elif state == CandleState.HLLH:
                state_score = -1.0  # Bearish
            elif state == CandleState.INSIDE:
                state_score = 0.0  # Neutral
            else:  # OUTSIDE
                state_score = 0.0  # Neutral (volatility, no clear direction)

            weighted_score += state_score * weight
            weights_sum += weight

            debug_info['timeframe_states'][tf] = state.name
            debug_info['timeframe_scores'][tf] = state_score

        # Normalize score to -1 to +1 range
        if weights_sum > 0:
            final_score = weighted_score / weights_sum
        else:
            final_score = 0.0

        # Calculate multi-timeframe alignment
        alignment = self.fractal_analyzer.get_multi_timeframe_alignment(states)
        debug_info['alignment'] = alignment
        debug_info['final_fractal_score'] = final_score

        return final_score, debug_info

    def calculate_indicator_score(self, timeframe: str = '5m') -> Tuple[float, Dict[str, Any]]:
        """
        Calculate indicator-based score for the trading timeframe

        Args:
            timeframe: timeframe to analyze (default: 5m)

        Returns:
            tuple of (score, indicators)
            score: -1 (bearish) to +1 (bullish)
            indicators: dict with all indicator values
        """
        candles = self.get_timeframe_candles(timeframe)
        if candles is None or len(candles) < 50:
            return 0.0, {}

        # Get indicator parameters from hyperparameters
        params = {
            'rsi_period': self.hp.get('rsi_period', 14),
            'macd_fast': self.hp.get('macd_fast', 12),
            'macd_slow': self.hp.get('macd_slow', 26),
            'macd_signal': self.hp.get('macd_signal', 9),
            'bb_period': self.hp.get('bb_period', 20),
            'bb_std': self.hp.get('bb_std', 2.0),
            'stoch_k': self.hp.get('stoch_k', 14),
            'stoch_d': self.hp.get('stoch_d', 3),
            'atr_period': self.hp.get('atr_period', 14),
        }

        # Calculate all indicators
        indicators = self.indicator_manager.calculate_all_indicators(candles, timeframe, params)

        # Calculate weighted score from indicators
        score = 0.0
        total_weight = 0.0

        # RSI contribution
        rsi_value = indicators['rsi']
        rsi_weight = self.hp.get('rsi_weight', 2.0)
        if rsi_value < 30:
            rsi_score = 1.0  # Oversold -> bullish
        elif rsi_value > 70:
            rsi_score = -1.0  # Overbought -> bearish
        else:
            # Linear interpolation between -1 and 1
            rsi_score = (50 - rsi_value) / 20.0
        score += rsi_score * rsi_weight
        total_weight += rsi_weight

        # MACD contribution
        macd_hist = indicators['macd']['histogram']
        macd_weight = self.hp.get('macd_weight', 2.5)
        macd_score = np.tanh(macd_hist * 10)  # Normalize with tanh
        score += macd_score * macd_weight
        total_weight += macd_weight

        # Bollinger Bands contribution
        bb_pos = indicators['bb']['position']
        bb_weight = self.hp.get('bb_weight', 1.5)
        if bb_pos < 0.2:
            bb_score = 1.0  # Near lower band -> bullish
        elif bb_pos > 0.8:
            bb_score = -1.0  # Near upper band -> bearish
        else:
            bb_score = (0.5 - bb_pos) * 2.0
        score += bb_score * bb_weight
        total_weight += bb_weight

        # Stochastic contribution
        stoch_k = indicators['stoch']['k']
        stoch_weight = self.hp.get('stoch_weight', 1.5)
        if stoch_k < 20:
            stoch_score = 1.0  # Oversold -> bullish
        elif stoch_k > 80:
            stoch_score = -1.0  # Overbought -> bearish
        else:
            stoch_score = (50 - stoch_k) / 30.0
        score += stoch_score * stoch_weight
        total_weight += stoch_weight

        # Heikin Ashi contribution
        ha_trend = indicators['ha']['trend_strength']
        ha_weight = self.hp.get('ha_weight', 2.0)
        score += ha_trend * ha_weight
        total_weight += ha_weight

        # Normalize final score
        if total_weight > 0:
            final_score = score / total_weight
        else:
            final_score = 0.0

        # Clamp to -1 to 1 range
        final_score = max(-1.0, min(1.0, final_score))

        return final_score, indicators

    def should_long(self) -> bool:
        """
        Determine if we should enter a LONG position

        Returns:
            bool: True if long conditions are met
        """
        # Calculate fractal score
        fractal_score, fractal_debug = self.calculate_fractal_score()

        # Calculate indicator score for trading timeframe
        indicator_score, indicators = self.calculate_indicator_score(self.timeframe)

        # Combine scores (equal weight by default, can be tuned)
        combined_score = (fractal_score + indicator_score) / 2.0

        # Get minimum score threshold from hyperparameters
        min_score = self.hp.get('min_score_long', 0.5)

        # Check if trend alignment is required
        require_alignment = self.hp.get('require_trend_alignment', True)
        min_trend_strength = self.hp.get('min_trend_strength', 0.2)

        # Store in vars for debugging
        self.vars['fractal_score'] = fractal_score
        self.vars['indicator_score'] = indicator_score
        self.vars['combined_score'] = combined_score
        self.vars['indicators'] = indicators

        # Entry conditions
        if combined_score > min_score:
            if require_alignment:
                # Check that fractal and indicators agree
                if fractal_score > min_trend_strength and indicator_score > min_trend_strength:
                    return True
            else:
                return True

        return False

    def should_short(self) -> bool:
        """
        Determine if we should enter a SHORT position

        Returns:
            bool: True if short conditions are met
        """
        # Calculate fractal score
        fractal_score, fractal_debug = self.calculate_fractal_score()

        # Calculate indicator score for trading timeframe
        indicator_score, indicators = self.calculate_indicator_score(self.timeframe)

        # Combine scores
        combined_score = (fractal_score + indicator_score) / 2.0

        # Get minimum score threshold from hyperparameters
        min_score = self.hp.get('min_score_short', 0.5)

        # Check if trend alignment is required
        require_alignment = self.hp.get('require_trend_alignment', True)
        min_trend_strength = self.hp.get('min_trend_strength', 0.2)

        # Store in vars for debugging
        self.vars['fractal_score'] = fractal_score
        self.vars['indicator_score'] = indicator_score
        self.vars['combined_score'] = combined_score
        self.vars['indicators'] = indicators

        # Entry conditions (negative score for short)
        if combined_score < -min_score:
            if require_alignment:
                # Check that fractal and indicators agree
                if fractal_score < -min_trend_strength and indicator_score < -min_trend_strength:
                    return True
            else:
                return True

        return False

    def go_long(self):
        """
        Execute LONG entry with dynamic position sizing and risk management
        """
        # Get ATR for dynamic stop-loss/take-profit
        candles = self.get_timeframe_candles(self.timeframe)
        atr_value = self.indicator_manager.calculate_atr(candles, self.hp.get('atr_period', 14))

        # Calculate stop-loss and take-profit levels
        sl_multiplier = self.hp.get('stop_loss_atr_multiplier', 2.0)
        tp_multiplier = self.hp.get('take_profit_atr_multiplier', 3.0)

        entry_price = self.price
        stop_loss_price = entry_price - (atr_value * sl_multiplier)
        take_profit_price = entry_price + (atr_value * tp_multiplier)

        # Calculate position size based on risk
        risk_per_trade = self.hp.get('risk_per_trade', 0.02)
        risk_amount = self.balance * risk_per_trade

        # Calculate quantity based on stop-loss distance
        stop_loss_distance = abs(entry_price - stop_loss_price)
        if stop_loss_distance > 0:
            qty = risk_amount / stop_loss_distance
        else:
            qty = self.balance * 0.01 / entry_price  # Fallback to 1% of balance

        # Ensure qty is positive and reasonable
        qty = abs(qty)

        # Limit position size to max % of balance
        max_position_pct = self.hp.get('max_position_pct', 0.95)
        max_qty = (self.balance * max_position_pct) / entry_price
        qty = min(qty, max_qty)

        # Round quantity appropriately
        qty = abs(utils.size_to_qty(qty * entry_price, entry_price, fee_rate=self.fee_rate))

        # Set entry order
        self.buy = qty, entry_price

        # Set stop-loss and take-profit
        self.stop_loss = qty, stop_loss_price
        self.take_profit = qty, take_profit_price

        # Store trade info for debugging
        self.vars['entry_price'] = entry_price
        self.vars['stop_loss_price'] = stop_loss_price
        self.vars['take_profit_price'] = take_profit_price
        self.vars['qty'] = qty
        self.vars['atr'] = atr_value

    def go_short(self):
        """
        Execute SHORT entry with dynamic position sizing and risk management
        """
        # Get ATR for dynamic stop-loss/take-profit
        candles = self.get_timeframe_candles(self.timeframe)
        atr_value = self.indicator_manager.calculate_atr(candles, self.hp.get('atr_period', 14))

        # Calculate stop-loss and take-profit levels
        sl_multiplier = self.hp.get('stop_loss_atr_multiplier', 2.0)
        tp_multiplier = self.hp.get('take_profit_atr_multiplier', 3.0)

        entry_price = self.price
        stop_loss_price = entry_price + (atr_value * sl_multiplier)
        take_profit_price = entry_price - (atr_value * tp_multiplier)

        # Calculate position size based on risk
        risk_per_trade = self.hp.get('risk_per_trade', 0.02)
        risk_amount = self.balance * risk_per_trade

        # Calculate quantity based on stop-loss distance
        stop_loss_distance = abs(stop_loss_price - entry_price)
        if stop_loss_distance > 0:
            qty = risk_amount / stop_loss_distance
        else:
            qty = self.balance * 0.01 / entry_price  # Fallback to 1% of balance

        # Ensure qty is positive and reasonable
        qty = abs(qty)

        # Limit position size to max % of balance
        max_position_pct = self.hp.get('max_position_pct', 0.95)
        max_qty = (self.balance * max_position_pct) / entry_price
        qty = min(qty, max_qty)

        # Round quantity appropriately
        qty = abs(utils.size_to_qty(qty * entry_price, entry_price, fee_rate=self.fee_rate))

        # Set entry order
        self.sell = qty, entry_price

        # Set stop-loss and take-profit
        self.stop_loss = qty, stop_loss_price
        self.take_profit = qty, take_profit_price

        # Store trade info for debugging
        self.vars['entry_price'] = entry_price
        self.vars['stop_loss_price'] = stop_loss_price
        self.vars['take_profit_price'] = take_profit_price
        self.vars['qty'] = qty
        self.vars['atr'] = atr_value

    def update_position(self):
        """
        Update position management (trailing stops, etc.)
        Called on every candle while position is open
        """
        # This can be extended to implement trailing stops or dynamic exit strategies
        pass

    def watch_list(self):
        """
        Values to display in watch list during backtesting/live trading

        Returns:
            list of dict with key-value pairs to display
        """
        return [
            {'key': 'Fractal Score', 'value': round(self.vars.get('fractal_score', 0), 3)},
            {'key': 'Indicator Score', 'value': round(self.vars.get('indicator_score', 0), 3)},
            {'key': 'Combined Score', 'value': round(self.vars.get('combined_score', 0), 3)},
            {'key': 'ATR', 'value': round(self.vars.get('atr', 0), 2)},
        ]
