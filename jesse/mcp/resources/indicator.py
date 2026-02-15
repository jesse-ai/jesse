"""
Jesse MCP Indicator Resources

This module provides comprehensive documentation for Jesse's extensive indicator
library through the MCP (Model Context Protocol). It serves as the complete
reference for all 140+ technical indicators available in Jesse.

The registered resources include:
- indicator-cheatsheet: Comprehensive overview and usage patterns
- indicator-details: Guidance for using indicator discovery tools
- indicator-workflow: Step-by-step guide for discovering and using indicators
- Detailed candle data structure and access patterns
- Comprehensive categorized indicator reference (Trend, Momentum, Volatility, etc.)
- Usage examples for major indicators in each category
- Import patterns and parameter conventions
- Integration with utility functions for signal generation

This resource is essential for strategy developers to discover available indicators
and understand proper usage patterns for technical analysis.
"""

import os
import inspect
import importlib.util

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

            ## Available Tools

            ### list_indicators Tool

            **Purpose**: Get a complete list of all technical indicators available in Jesse.

            **Usage**:
            ```python
            result = list_indicators()
            ```

            **Returns**: A structured response containing:
            - `status`: "success" or "error"
            - `count`: Number of available indicators (140+)
            - `indicators`: Array of all indicator names (sorted alphabetically)
            - `message`: Descriptive message about the result

            **Example Response**:
            ```json
            {
                "status": "success",
                "count": 147,
                "indicators": ["sma", "ema", "rsi", "macd", "bollinger_bands", ...],
                "message": "Found 147 indicators available in Jesse"
            }
            ```

            This tool provides the most reliable and up-to-date way to discover all available indicators programmatically.

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

            #### Method 1: Use the list_indicators Tool

            The most convenient way to get a complete list of all available indicators is using the `list_indicators` MCP tool:

            ```python
            # Use the list_indicators tool to get all available indicators
            result = list_indicators()
            # Returns: {"status": "success", "count": 140, "indicators": ["sma", "ema", "rsi", ...], "message": "..."}
            ```

            This tool provides a programmatically generated list of all 140+ indicators available in Jesse.

            #### Method 2: Explore by Category Patterns

            For manual exploration, indicators are organized by category:

            - **Trend**: sma, ema, dema, tema, wma, hma, kama, alma, frama, vidya, mcginley_dynamic
            - **Momentum**: rsi, macd, stochastic, cci, mfi, ao, willr, roc, mom, tsi, uo
            - **Volatility**: atr, natr, bollinger_bands, keltner, donchian, chop, mass, vpci
            - **Volume**: vwap, vwma, obv, ad, adosc, cmf, kvo
            - **Statistical**: beta, correl, linearreg, zscore, stddev, var, skew, kurtosis
            - **Specialized**: fisher, schaff_trend_cycle, squeeze_momentum, hurst_exponent, damiani_volatmeter, safezonestop, kaufmanstop


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

    @mcp.resource("jesse://indicator-details")
    def indicator_details():
        """
        Get detailed information about any specific indicator.

        This resource provides comprehensive documentation for individual indicators
        including parameters, return values, usage examples, and trading interpretations.
        Use the list_indicators tool to discover available indicator names.
        """
        return """
        # Individual Indicator Details

        This resource explains how to access detailed documentation for any Jesse indicator.

        ## How to Get Indicator Details

        Use the `get_indicator_details` tool with an indicator name to get comprehensive documentation:

        ```python
        # Get detailed information about RSI
        result = get_indicator_details("rsi")

        # Get detailed information about MACD
        result = get_indicator_details("macd")
        ```

        ## Available Indicators

        Use the `list_indicators` tool to get a complete list of all 177 available indicators.

        ## Information Provided by get_indicator_details Tool

        For each indicator, the tool provides:
        - Complete function signature with parameters
        - Parameter descriptions and default values
        - Return value structure and types
        - Parsed docstring information
        - Usage examples
        - Implementation details

            ## Common Indicators to Explore

        Popular indicators include: rsi, macd, sma, ema, bollinger_bands, stochastic, atr, cci, etc.
        """

    @mcp.resource("jesse://indicator-workflow")
    def indicator_workflow():
        """
        Get guidance for discovering and using technical indicators in strategies.

        This resource provides a systematic workflow for LLMs to properly integrate
        indicators into trading strategies using the available MCP tools.
        """
        return """
        # Indicator Discovery and Usage Workflow

        Follow this systematic approach to ensure accurate indicator usage in strategies:

        ## Step 1: List All Available Indicators

        **Always start here** - Never assume indicator names or availability.

        ```python
        # Use the list_indicators tool to discover all available indicators
        result = list_indicators()
        # Returns: {"status": "success", "count": 177, "indicators": ["sma", "ema", "rsi", ...]}
        ```

        **Why?** Jesse has 177 indicators. Guessing names leads to errors.

        ## Step 2: Select Required Indicators

        Based on your trading strategy requirements, choose appropriate indicators from the list.
        Common categories include:
        - **Trend**: sma, ema, macd, adx
        - **Momentum**: rsi, stochastic, cci, mfi
        - **Volatility**: bollinger_bands, atr, keltner
        - **Volume**: obv, vwap, volume

        ## Step 3: Get Detailed Indicator Information

        **For each selected indicator**, use the get_indicator_details tool:

        ```python
        # Get complete details for each indicator you plan to use
        rsi_details = get_indicator_details("rsi")
        macd_details = get_indicator_details("macd")
        bb_details = get_indicator_details("bollinger_bands")
        ```

        This provides:
        - **Function signature** with exact parameter names and defaults
        - **Return type** (float, numpy array, or namedtuple)
        - **Parameter specifications** (types, defaults, requirements)
        - **Usage examples** with proper syntax

        ## Step 4: Implement Indicators Correctly

        Use the details to write proper indicator calls:

        ### Example: RSI (returns single float)
        ```python
        # From get_indicator_details("rsi"):
        # signature: (candles, period=14, source_type="close", sequential=False) -> float

        rsi_value = ta.rsi(self.candles, period=14)
        # Returns: float between 0-100

        if rsi_value < 30:
            # Oversold condition
            return True
        ```

        ### Example: MACD (returns namedtuple)
        ```python
        # From get_indicator_details("macd"):
        # signature: (candles, fast_period=12, slow_period=26, signal_period=9) -> MACD(macd, signal, hist)

        macd_result = ta.macd(self.candles)
        # Returns: MACD(macd=..., signal=..., hist=...)

        if macd_result.hist > 0 and macd_result.macd > macd_result.signal:
            # Bullish MACD crossover
            return True
        ```

        ### Example: Bollinger Bands (returns namedtuple)
        ```python
        # From get_indicator_details("bollinger_bands"):
        # signature: (candles, period=20, devup=2.0, devdn=2.0) -> BollingerBands(upper, middle, lower)

        bb = ta.bollinger_bands(self.candles)
        # Returns: BollingerBands(upper=..., middle=..., lower=...)

        price = self.close
        if price <= bb.lower:
            # Price touched lower band
            return True
        ```

        ## Step 5: Handle Sequential Data

        For indicators that support sequential mode:

        ```python
        # Most indicators support sequential=True for full series
        rsi_series = ta.rsi(self.candles, period=14, sequential=True)
        # Returns: numpy array of all RSI values

        # Access current value
        current_rsi = rsi_series[-1]

        # Access previous values for trend analysis
        prev_rsi = rsi_series[-2]
        ```

        ## Common Mistakes to Avoid

        ❌ **Wrong**: Guessing indicator names
        ```python
        ta.RSI(self.candles)  # Wrong case
        ta.relative_strength_index(self.candles)  # Wrong name
        ```

        ✅ **Correct**: Use tools to verify
        ```python
        # Check available indicators first
        indicators = list_indicators()
        # Then get details
        details = get_indicator_details("rsi")
        # Then use correctly
        rsi = ta.rsi(self.candles, period=14)
        ```

        ❌ **Wrong**: Misunderstanding return types
        ```python
        macd, signal, hist = ta.macd(self.candles)  # Wrong - returns namedtuple
        rsi, stoch = ta.rsi(self.candles), ta.stochastic(self.candles)  # Wrong types
        ```

        ✅ **Correct**: Check return types first
        ```python
        macd_result = ta.macd(self.candles)
        macd_value = macd_result.macd  # Access namedtuple field
        signal_value = macd_result.signal
        hist_value = macd_result.hist
        ```

        ## Pro Tips

        1. **Always verify** indicator availability before using
        2. **Check return types** - many indicators return namedtuples, not simple values
        3. **Use defaults** unless you have specific requirements
        4. **Test with sequential=True** for debugging indicator values
        5. **Document your indicator choices** in strategy comments

        Following this workflow ensures accurate, error-free indicator implementation in your strategies.
        """