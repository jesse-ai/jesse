"""
Jesse MCP Indicator Resources

This module provides comprehensive documentation for Jesse's extensive indicator
library through the MCP (Model Context Protocol). It serves as the complete
reference for all 140+ technical indicators available in Jesse.

The registered resource includes:
- Detailed candle data structure and access patterns
- Comprehensive categorized indicator reference (Trend, Momentum, Volatility, etc.)
- Usage examples for major indicators in each category
- Import patterns and parameter conventions
- Integration with utility functions for signal generation

This resource is essential for strategy developers to discover available indicators
and understand proper usage patterns for technical analysis.
"""

def register_indicator_resources(mcp):

    @mcp.resource("jesse://indicator-cheatsheet")
    def indicator_cheatsheet():
        """
        Get comprehensive reference for Jesse's technical indicators.

        This reference covers all major indicator categories with usage examples,
        candle data access patterns, and integration with utility functions.
        Essential for strategy development and technical analysis.
        """
        return """
            Jesse Indicator Reference

            Indicators are available through:

            import jesse.indicators as ta

            ## Candle Data Structure

            Indicators commonly operate on: self.candles

            Candle data is stored as a numpy array with shape (time, OHLCV):

            - **Index 0**: Timestamp (Unix timestamp)
            - **Index 1**: Open price
            - **Index 2**: Close price
            - **Index 3**: High price
            - **Index 4**: Low price
            - **Index 5**: Volume

            ### Direct Access Examples:
            ```python
            # Access current candle data
            current_close = self.candles[-1, 2]  # Latest close price
            current_high = self.candles[-1, 3]   # Latest high price
            previous_close = self.candles[-2, 2] # Previous close price

            # Access price series for indicators
            close_prices = self.candles[:, 2]    # All close prices
            high_prices = self.candles[:, 3]     # All high prices
            ```

            ### Common Price Calculations:
            ```python
            # Typical price (HLC/3)
            hlc3 = (self.candles[:, 3] + self.candles[:, 4] + self.candles[:, 2]) / 3

            # Mid price (HL/2)
            hl2 = (self.candles[:, 3] + self.candles[:, 4]) / 2

            # Average price (OHLC/4)
            ohlc4 = (self.candles[:, 1] + self.candles[:, 3] + self.candles[:, 4] + self.candles[:, 2]) / 4
            ```

            ### Using CANDLE_SOURCE_MAPPING:
            ```python
            from jesse.constants import CANDLE_SOURCE_MAPPING

            # Access different price series
            closes = CANDLE_SOURCE_MAPPING['close'](self.candles)
            highs = CANDLE_SOURCE_MAPPING['high'](self.candles)
            hl2_prices = CANDLE_SOURCE_MAPPING['hl2'](self.candles)
            hlc3_prices = CANDLE_SOURCE_MAPPING['hlc3'](self.candles)
            ```

            ## Essential Indicators

            Core indicators that LLMs should prioritize for strategy development:

            ### Trend Following
            ```python
            ta.sma(self.candles, period=20)      # Simple Moving Average
            ta.ema(self.candles, period=20)      # Exponential Moving Average
            ta.wma(self.candles, period=20)      # Weighted Moving Average
            ta.hma(self.candles, period=20)      # Hull Moving Average
            ```

            ### Momentum & Oscillators
            ```python
            ta.rsi(self.candles, period=14)      # Relative Strength Index (0-100)
            ta.macd(self.candles)                 # MACD (returns: macd, signal, histogram)
            ta.stochastic(self.candles)           # Stochastic (%K, %D)
            ta.cci(self.candles, period=20)       # Commodity Channel Index
            ta.mfi(self.candles, period=14)       # Money Flow Index
            ta.willr(self.candles, period=14)     # Williams %R
            ```

            ### Volatility & Channels
            ```python
            ta.atr(self.candles, period=14)       # Average True Range
            ta.bollinger_bands(self.candles)       # Bollinger Bands (upper, middle, lower)
            ta.keltner(self.candles)              # Keltner Channels
            ta.donchian(self.candles)             # Donchian Channels
            ```

            ### Volume & Flow
            ```python
            ta.vwap(self.candles)                 # Volume Weighted Average Price
            ta.obv(self.candles)                  # On Balance Volume
            ta.ad(self.candles)                   # Accumulation/Distribution Line
            ```

            ### Trend Strength
            ```python
            ta.adx(self.candles, period=14)       # Average Directional Index
            ta.di(self.candles, period=14)        # Directional Indicators (+DI, -DI)
            ta.supertrend(self.candles)           # SuperTrend
            ta.ichimoku_cloud(self.candles)       # Ichimoku Cloud (full system)
            ```

            ### Specialized (Use Sparingly)
            ```python
            ta.fisher(self.candles, period=10)   # Fisher Transform
            ta.squeeze_momentum(self.candles)    # TTM Squeeze Momentum
            ta.safezonestop(self.candles)        # SafeZone Stop Loss
            ```

            ## Indicator Discovery

            **Jesse provides 140+ indicators total** across these categories:
            - **Trend**: 11+ moving averages (SMA, EMA, DEMA, TEMA, KAMA, ALMA, FRAMA, VIDYA, etc.)
            - **Momentum**: 11+ oscillators (RSI, MACD, Stochastic, CCI, MFI, AO, Williams %R, ROC, MOM, TSI, UO)
            - **Volatility**: 9+ indicators (ATR, NATR, Bollinger Bands, Keltner, Donchian, CHOP, Mass Index, VPCI)
            - **Volume**: 7+ indicators (VWAP, VWMA, OBV, AD, ADOSC, CMF, KVO)
            - **Trend Strength**: 8+ indicators (ADX, DI, DX, PSAR, SuperTrend, Ichimoku, Pivot Points, Support/Resistance)
            - **Statistical**: 9+ indicators (Beta, Correlation, Linear Regression, Z-Score, Standard Deviation, Variance, Skewness, Kurtosis)
            - **Specialized**: 8+ advanced indicators (Fisher Transform, Schaff Cycle, Squeeze Momentum, Hurst Exponent, Damiani Volatmeter, SafeZone Stop, Kaufman Stop)

            ### Finding Specific Indicator Names

            To discover exact indicator names for specialized use cases:

            ```python
            # Method 1: Check available indicators programmatically
            import jesse.indicators as ta
            print(dir(ta))  # Lists all available indicator names

            # Method 2: Explore by category patterns
            # Trend indicators: sma, ema, dema, tema, wma, hma, kama, alma, frama, vidya, mcginley_dynamic
            # Momentum: rsi, macd, stochastic, cci, mfi, ao, willr, roc, mom, tsi, uo
            # Volatility: atr, natr, bollinger_bands, keltner, donchian, chop, mass, vpci
            # Volume: vwap, vwma, obv, ad, adosc, cmf, kvo
            # Statistical: beta, correl, linearreg, zscore, stddev, var, skew, kurtosis
            # Specialized: fisher, schaff_trend_cycle, squeeze_momentum, hurst_exponent, damiani_volatmeter, safezonestop, kaufmanstop
            ```

            **Note**: Focus on the essential indicators above for robust strategies. Use advanced indicators only when you have a specific need and understand their behavior thoroughly. All indicators are available via `import jesse.indicators as ta` followed by `ta.indicator_name()`.

            ## Usage Notes

            - **Import**: `import jesse.indicators as ta`
            - **Data Input**: Most indicators take `self.candles` as first parameter
            - **Returns**: Single value, tuple, or numpy array depending on indicator
            - **Parameters**: Check individual indicator docstrings for available parameters

            Cross detection and other utility functions:
            ```python
            from jesse import utils
            utils.crossed(series1, series2)
            ```

            See `jesse://utilities` resource for comprehensive utils documentation.
            """