"""
Jesse Indicator Tools

This module provides MCP tools for working with Jesse's technical indicators.

The tools include:
- list_indicators: List all available technical indicators in Jesse
- get_indicator_details: Get detailed information about a specific indicator
"""

from .services import (
    list_indicators_service,
    get_indicator_details_service
)

def register_indicator_tools(mcp):
    """
    Register the indicator tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def list_indicators() -> dict:
        """
        Retrieve a complete list of all technical indicators available in Jesse.

        Discovers and returns all 140+ technical indicators available through
        the `jesse.indicators` module. This is the authoritative source for
        discovering indicator names before using `get_indicator_details()`.

        Essential for strategy development as Jesse provides extensive indicator
        coverage across trend, momentum, volatility, volume, and specialized categories.

        Parameters:
            None

        Returns:
            dict: Complete indicator catalog with metadata:

            Success Response:
            {
                "status": "success",
                "count": 147,                    // Total number of available indicators
                "indicators": [                  // Alphabetically sorted array of indicator names
                    "sma", "ema", "rsi", "macd", "bollinger_bands",
                    "stochastic", "cci", "atr", "adx", "supertrend",
                    // ... all 140+ indicator names
                ],
                "message": "Found 147 indicators available in Jesse"
            }

            Error Response:
            {
                "status": "error",
                "error": "detailed_error_message",
                "message": "Failed to list indicators"
            }

            Shape: {
                "status": "success|error",
                "count": int|undefined,
                "indicators": array[string]|undefined,
                "error": string|undefined,
                "message": string
            }

        Raises:
            ImportError: If jesse.indicators module cannot be imported
            AttributeError: If indicator module structure is unexpected

        Indicator Categories:
            - **Trend (11+)**: Moving averages (SMA, EMA, DEMA, TEMA, WMA, HMA, KAMA, ALMA, FRAMA, VIDYA, McGinley)
            - **Momentum (11+)**: Oscillators (RSI, MACD, Stochastic, CCI, MFI, AO, Williams %R, ROC, MOM, TSI, UO)
            - **Volatility (9+)**: Bands & ranges (ATR, NATR, Bollinger Bands, Keltner, Donchian, CHOP, Mass Index, VPCI)
            - **Volume (7+)**: Flow indicators (VWAP, VWMA, OBV, AD, ADOSC, CMF, KVO)
            - **Trend Strength (8+)**: Direction indicators (ADX, DI, DX, PSAR, SuperTrend, Ichimoku, Pivot Points)
            - **Statistical (9+)**: Math indicators (Beta, Correlation, Linear Regression, Z-Score, StdDev, Variance)
            - **Specialized (8+)**: Advanced indicators (Fisher Transform, Schaff Cycle, Squeeze Momentum, Hurst)

        Usage Pattern:
            1. Call list_indicators() to discover available indicators
            2. For each indicator you want to use, call get_indicator_details(name)
            3. Use the detailed information to implement indicators correctly

        Example:
            >>> # Discover all available indicators
            >>> result = list_indicators()
            >>> if result["status"] == "success":
            ...     print(f"Found {result['count']} indicators")
            ...     # Find trend indicators
            ...     trend_indicators = [i for i in result["indicators"]
            ...                        if i in ["sma", "ema", "macd", "adx"]]
            ...     print(f"Trend indicators: {trend_indicators}")

            >>> # Check if specific indicators exist
            >>> available = result["indicators"]
            >>> has_rsi = "rsi" in available
            >>> has_bollinger = "bollinger_bands" in available
            >>> print(f"RSI available: {has_rsi}, Bollinger Bands: {has_bollinger}")

        Note:
            Always use this tool first when developing strategies - never assume
            indicator names or availability. Jesse's indicator collection is extensive
            but names may not match common trading platform conventions.
        """
        return list_indicators_service()

    @mcp.tool()
    def get_indicator_details(indicator_name: str) -> dict:
        """
        Retrieve comprehensive documentation for a specific technical indicator.

        Analyzes the indicator's source code to provide complete function signature,
        parameter specifications, return types, and usage examples. Essential for
        correct indicator implementation in trading strategies.

        Use list_indicators() first to discover available indicator names, then
        use this tool to get implementation details for each indicator you plan to use.

        Parameters:
            indicator_name (str): Exact name of the indicator as returned by list_indicators()
                Examples: "rsi", "macd", "sma", "bollinger_bands", "stochastic", "atr"
                Shape: String matching available indicator names exactly

        Returns:
            dict: Complete indicator documentation and metadata:

            Success Response:
            {
                "status": "success",
                "indicator_name": "rsi",
                "signature": "(candles, period=14, source_type='close', sequential=False) -> float",
                "parameters": {
                    "candles": {
                        "name": "candles",
                        "default": null,
                        "annotation": "numpy.ndarray",
                        "kind": "POSITIONAL_OR_KEYWORD"
                    },
                    "period": {
                        "name": "period",
                        "default": 14,
                        "annotation": "int",
                        "kind": "POSITIONAL_OR_KEYWORD"
                    },
                    // ... all parameters with details
                },
                "return_annotation": "float",
                "docstring": "Relative Strength Index indicator...",
                "namedtuple_info": null,  // or namedtuple details if applicable
                "usage_example": "import jesse.indicators as ta\n\nresult = ta.rsi(self.candles, period=14)",
                "file_path": "/path/to/jesse/indicators/rsi.py",
                "message": "Successfully retrieved details for indicator: rsi"
            }

            Error Response:
            {
                "status": "error",
                "error": "Indicator 'invalid_name' not found",
                "indicator_name": "invalid_name",
                "message": "Could not find indicator file: /path/to/indicators/invalid_name.py"
            }

            Shape: {
                "status": "success|error",
                "indicator_name": string,
                "signature": string|undefined,
                "parameters": object|undefined,
                "return_annotation": string|undefined,
                "docstring": string|undefined,
                "namedtuple_info": object|undefined,
                "usage_example": string|undefined,
                "file_path": string|undefined,
                "error": string|undefined,
                "message": string
            }

            NamedTuple Info (for complex indicators):
            {
                "name": "MACD",
                "fields": ["macd", "signal", "hist"],
                "defaults": {}
            }

        Raises:
            FileNotFoundError: If indicator file doesn't exist
            ImportError: If indicator module cannot be loaded
            AttributeError: If indicator function not found in module

        Parameter Details:
            - **candles**: Numpy array with shape (time, OHLCV) - always first parameter
            - **sequential**: Bool - if True returns full series, if False returns single value
            - **source_type**: String - price source ("close", "open", "high", "low", "hl2", "hlc3", "ohlc4")
            - **period**: Int - lookback period for calculations
            - Other parameters vary by indicator (check signature)

        Return Types:
            - **Single float/int**: Most oscillators (RSI, CCI, MFI, etc.)
            - **NamedTuple**: Complex indicators (MACD, BollingerBands, Stochastic, etc.)
            - **Numpy array**: When sequential=True
            - **Tuple**: Some multi-value indicators

        Usage Workflow:
            1. list_indicators() → discover available indicators
            2. get_indicator_details(name) → get implementation details
            3. Implement with correct parameters and handle return types

        Example:
            >>> # Get RSI details
            >>> rsi_info = get_indicator_details("rsi")
            >>> if rsi_info["status"] == "success":
            ...     print(f"Signature: {rsi_info['signature']}")
            ...     print(f"Returns: {rsi_info['return_annotation']}")
            ...     print(f"Usage:\\n{rsi_info['usage_example']}")

            >>> # Get MACD details (returns namedtuple)
            >>> macd_info = get_indicator_details("macd")
            >>> if macd_info["status"] == "success":
            ...     nt_info = macd_info["namedtuple_info"]
            ...     print(f"MACD returns: {nt_info['name']} with fields: {nt_info['fields']}")

            >>> # Check parameter defaults
            >>> params = macd_info["parameters"]
            >>> fast_period_default = params["fast_period"]["default"]
            >>> slow_period_default = params["slow_period"]["default"]
            >>> print(f"MACD defaults: fast={fast_period_default}, slow={slow_period_default}")

        Common Patterns:
            >>> # Single value indicator (RSI)
            >>> rsi = ta.rsi(self.candles, period=14)  # Returns float

            >>> # NamedTuple indicator (MACD)
            >>> macd = ta.macd(self.candles)  # Returns MACD(macd=..., signal=..., hist=...)
            >>> if macd.hist > 0:  # Access fields
            ...     return True

            >>> # Sequential data
            >>> rsi_series = ta.rsi(self.candles, sequential=True)  # Returns numpy array
            >>> current_rsi = rsi_series[-1]  # Latest value
            >>> prev_rsi = rsi_series[-2]     # Previous value

        Note:
            Always check the return_annotation and namedtuple_info to handle
            return values correctly. Many indicators return namedtuples, not simple values.
        """
        return get_indicator_details_service(indicator_name)