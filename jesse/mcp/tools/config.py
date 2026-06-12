"""
Jesse Configuration Management Tools

This module provides MCP tools for managing Jesse configuration,
using the config controller endpoints like the dashboard does.

The configuration includes:
- Backtest settings (logging, warmup candles, exchanges)
- Live trading settings
- General Jesse settings
"""

from .services import (
    get_config_service,
    update_config_service,
    get_backtest_config_service,
    get_live_config_service,
    get_optimization_config_service
)


def register_config_tools(mcp):
    """
    Register the configuration management tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def get_config() -> dict:
        """
        Retrieve the complete Jesse configuration from the database.

        Loads the entire Jesse configuration object that controls backtest execution,
        live trading behavior, and optimization settings. This includes exchange settings,
        logging preferences, fee structures, leverage configurations, and more.

        This is the primary method for accessing all Jesse system configuration
        in a single call, using the same endpoint as the dashboard.

        Parameters:
            None

        Returns:
            dict: Complete configuration object with structured data:

            Success Response:
            {
                "status": "success",
                "config": {
                    "data": {
                        "backtest": {
                            "warm_up_candles": int,
                            "logging": {
                                "order_submission": bool,
                                "trading_candles": bool,
                                "shorter_period_candles": bool,
                                "position_reduced": bool,
                                "position_opened": bool,
                                "position_closed": bool,
                                "order_execution": bool,
                                "position_increased": bool,
                                "balance_update": bool,
                                "order_cancellation": bool
                            },
                            "exchanges": {
                                "ExchangeName": {
                                    "balance": float,
                                    "fee": float,
                                    "type": "spot|futures",
                                    "futures_leverage": int,
                                    "futures_leverage_mode": "cross|isolated"
                                }
                            }
                        },
                        "live": {
                            "warm_up_candles": int,
                            "exchanges": { /* Live trading exchange configs */ }
                        },
                        "optimization": {
                            "cpu_cores": int,
                            "best_candidates_count": int,
                            "warm_up_candles": int,
                            "trials": int,
                            "exchange": {
                                "futures_leverage": int,
                                "fee": float,
                                "futures_leverage_mode": "cross|isolated",
                                "balance": float,
                                "type": "futures"
                            },
                            "objective_function": "sharpe|sortino|calmar|max_drawdown"
                        }
                    }
                },
                "message": "Configuration loaded successfully"
            }

            Error Response:
            {
                "status": "error",
                "message": "Authentication failed" | "Failed to load config: [details]"
            }

            Shape: {
                "status": "success|error",
                "config": object|undefined,
                "message": string
            }

        Raises:
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Returns the complete configuration as stored in database
            - Configuration controls all aspects of Jesse operation
            - Changes are applied immediately when updated
            - Use specific section getters (get_backtest_config, etc.) for targeted access

        Configuration Sections:
            - **backtest**: Settings for backtesting (warmup, logging, exchanges)
            - **live**: Settings for live trading (exchanges, notifications)
            - **optimization**: Settings for hyperparameter optimization (CPU cores, trials)

        Example:
            >>> # Get complete configuration
            >>> config = get_config()
            >>> if config["status"] == "success":
            ...     backtest_settings = config["config"]["data"]["backtest"]
            ...     fee_rate = backtest_settings["exchanges"]["Binance Spot"]["fee"]
            ...     print(f"Current fee rate: {fee_rate}")

            >>> # Access specific nested values
            >>> warm_up = config["config"]["data"]["backtest"]["warm_up_candles"]
            >>> logging_enabled = config["config"]["data"]["backtest"]["logging"]["trading_candles"]
        """
        return get_config_service()

    @mcp.tool()
    def update_config(config: str) -> dict:
        """
        Update the Jesse configuration in the database with new settings.

        Saves a complete configuration object to the Jesse database, replacing
        existing configuration. This controls how backtests, live trading,
        and optimization behave. Changes are applied immediately and persist
        until explicitly modified.

        Use get_config() first to retrieve current configuration, modify it,
        then save with this function. Only modified sections need to be included.

        Parameters:
            config (str): JSON string containing complete configuration object.
                Must follow Jesse configuration schema with "data" root key.
                Shape: JSON string representing:
                {
                    "data": {
                        "backtest": { /* backtest config */ },
                        "live": { /* live config */ },
                        "optimization": { /* optimization config */ }
                    }
                }

        Returns:
            dict: Update confirmation with status:

            Success Response:
            {
                "status": "success",
                "message": "Configuration updated successfully"
            }

            Error Response:
            {
                "status": "error",
                "message": "Authentication failed" | "Failed to update config: [details]"
            }

            Error Response (JSON parsing):
            {
                "status": "error",
                "error": "Invalid JSON format",
                "details": "[parsing error details]",
                "message": "Failed to parse configuration JSON"
            }

            Shape: {
                "status": "success|error",
                "message": string,
                "error": string|undefined,
                "details": string|undefined
            }

        Raises:
            JSONDecodeError: If config parameter is not valid JSON
            ValidationError: If configuration structure is invalid
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Completely replaces existing configuration in database
            - Changes are applied immediately to all Jesse operations
            - Configuration persists across application restarts
            - Invalid configurations may cause runtime errors in backtests/live trading

        Configuration Validation:
            - Must include "data" root key
            - Exchange names must match supported exchanges
            - Numeric values must be within valid ranges
            - Boolean flags control various logging and behavior settings

        Workflow:
            1. get_config() → retrieve current configuration
            2. Modify configuration object as needed
            3. json.dumps() → convert to JSON string
            4. update_config() → save changes
            5. get_config() → verify changes were applied

        Example:
            >>> import json
            >>> # Get current config
            >>> current = get_config()
            >>> config_data = current["config"]
            >>>
            >>> # Modify backtest settings
            >>> config_data["data"]["backtest"]["warm_up_candles"] = 300
            >>> config_data["data"]["backtest"]["exchanges"]["Binance Spot"]["fee"] = 0.001
            >>>
            >>> # Save changes
            >>> result = update_config(json.dumps(config_data))
            >>> if result["status"] == "success":
            ...     print("Configuration updated successfully")
            ... else:
            ...     print(f"Update failed: {result['message']}")
            
        """
        return update_config_service(config)

    @mcp.tool()
    def get_backtest_config() -> dict:
        """
        Retrieve backtest-specific configuration settings.

        Convenience method that extracts and returns only the backtest configuration
        section from the complete Jesse configuration. This includes exchange settings,
        logging preferences, warmup candles, and other backtesting parameters.

        Use this instead of get_config() when you only need backtest settings,
        as it provides cleaner access to backtest-specific configuration.

        Parameters:
            None

        Returns:
            dict: Backtest configuration section with detailed settings:

            Success Response:
            {
                "status": "success",
                "section": "backtest",
                "config": {
                    "warm_up_candles": int,  // Candles used for indicator warm-up (default: 240)
                    "logging": {
                        "order_submission": bool,     // Log order submissions
                        "trading_candles": bool,      // Log trading candle events
                        "shorter_period_candles": bool, // Log shorter timeframe candles
                        "position_reduced": bool,     // Log position reductions
                        "position_opened": bool,      // Log position openings
                        "position_closed": bool,      // Log position closings
                        "order_execution": bool,      // Log order executions
                        "position_increased": bool,   // Log position increases
                        "balance_update": bool,       // Log balance updates
                        "order_cancellation": bool    // Log order cancellations
                    },
                    "exchanges": {
                        "ExchangeName": {
                            "balance": float,           // Starting balance in base currency
                            "fee": float,               // Trading fee rate (e.g., 0.0004 = 0.04%)
                            "type": "spot|futures",     // Exchange type
                            "futures_leverage": int,    // Leverage for futures (default: 1)
                            "futures_leverage_mode": "cross|isolated"  // Leverage mode
                        }
                    }
                },
                "message": "Configuration section 'backtest' loaded successfully"
            }

            Error Response:
            {
                "status": "error",
                "section": "backtest",
                "message": "Configuration section 'backtest' not found",
                "available_sections": ["backtest", "live", "optimization"]
            }

            Shape: {
                "status": "success|error",
                "section": string,
                "config": object|undefined,
                "message": string,
                "available_sections": array[string]|undefined
            }

        Raises:
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Extracts only the "backtest" section from full configuration
            - Provides same data structure as get_config()["config"]["data"]["backtest"]
            - Useful for backtest-specific configuration management
            - Settings control how backtests execute and what gets logged

        Key Settings:
            - **warm_up_candles**: Candles used to initialize indicators (affects backtest start)
            - **logging**: Controls what events are logged during backtest execution
            - **exchanges**: Per-exchange settings for balance, fees, leverage

        Example:
            >>> # Get backtest configuration
            >>> bt_config = get_backtest_config()
            >>> if bt_config["status"] == "success":
            ...     warmup = bt_config["config"]["warm_up_candles"]
            ...     fee = bt_config["config"]["exchanges"]["Binance Spot"]["fee"]
            ...     leverage = bt_config["config"]["exchanges"]["Binance Futures"]["futures_leverage"]
            ...     print(f"Warmup: {warmup} candles, Fee: {fee}, Leverage: {leverage}x")

            >>> # Check logging settings
            >>> logging = bt_config["config"]["logging"]
            >>> if logging["trading_candles"]:
            ...     print("Detailed candle logging enabled")
        """
        return get_backtest_config_service()

    @mcp.tool()
    def get_live_config() -> dict:
        """
        Retrieve live trading configuration settings.

        Convenience method that extracts and returns only the live trading configuration
        section from the complete Jesse configuration. This includes exchange settings
        for live trading, notification preferences, and live-specific parameters.

        Use this instead of get_config() when you only need live trading settings,
        as it provides cleaner access to live-trading-specific configuration.

        Parameters:
            None

        Returns:
            dict: Live trading configuration section:

            Success Response:
            {
                "status": "success",
                "section": "live",
                "config": {
                    "warm_up_candles": int,  // Candles for indicator initialization in live trading
                    "exchanges": {
                        "ExchangeName": {
                            "balance": float,           // Live trading account balance
                            "fee": float,               // Live trading fee rate
                            "type": "spot|futures",     // Exchange type for live trading
                            "futures_leverage": int,    // Futures leverage for live trading
                            "futures_leverage_mode": "cross|isolated",
                            // Additional live-specific settings...
                        }
                    },
                    // Additional live trading settings like notifications, risk limits, etc.
                },
                "message": "Configuration section 'live' loaded successfully"
            }

            Error Response:
            {
                "status": "error",
                "section": "live",
                "message": "Configuration section 'live' not found",
                "available_sections": ["backtest", "live", "optimization"]
            }

            Shape: {
                "status": "success|error",
                "section": string,
                "config": object|undefined,
                "message": string,
                "available_sections": array[string]|undefined
            }

        Raises:
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Extracts only the "live" section from full configuration
            - Provides same data structure as get_config()["config"]["data"]["live"]
            - Settings control live trading execution and behavior
            - Separate from backtest settings for safety

        Key Settings:
            - **warm_up_candles**: Candles needed for indicator initialization in live mode
            - **exchanges**: Live trading account settings (real balance, actual fees)
            - **notifications**: Alert and notification preferences for live trading

        Safety Notes:
            - Live configuration should use real account balances and fees
            - Always verify live settings before deploying strategies
            - Live and backtest configurations are kept separate intentionally

        Example:
            >>> # Get live trading configuration
            >>> live_config = get_live_config()
            >>> if live_config["status"] == "success":
            ...     live_balance = live_config["config"]["exchanges"]["Binance Spot"]["balance"]
            ...     live_fee = live_config["config"]["exchanges"]["Binance Spot"]["fee"]
            ...     print(f"Live balance: ${live_balance}, Fee: {live_fee}")

            >>> # Check if live config exists
            >>> if live_config["status"] == "error":
            ...     print("Live configuration not set up yet")
            ...     print(f"Available sections: {live_config['available_sections']}")
        """
        return get_live_config_service()

    @mcp.tool()
    def get_optimization_config() -> dict:
        """
        Retrieve hyperparameter optimization configuration settings.

        Convenience method that extracts and returns only the optimization configuration
        section from the complete Jesse configuration. This includes CPU core allocation,
        trial counts, objective functions, and optimization-specific exchange settings.

        Use this instead of get_config() when you only need optimization settings,
        as it provides cleaner access to optimization-specific configuration.

        Parameters:
            None

        Returns:
            dict: Optimization configuration section with detailed settings:

            Success Response:
            {
                "status": "success",
                "section": "optimization",
                "config": {
                    "cpu_cores": int,              // CPU cores to use (default: 1)
                    "best_candidates_count": int,  // Number of best results to keep (default: 20)
                    "warm_up_candles": int,        // Candles for indicator warm-up (default: 210)
                    "trials": int,                 // Total optimization trials (default: 200)
                    "exchange": {
                        "futures_leverage": int,    // Leverage for optimization (default: 5)
                        "fee": float,               // Fee rate for optimization (default: 0.0006)
                        "futures_leverage_mode": "cross|isolated",
                        "balance": float,           // Starting balance (default: 10000)
                        "type": "futures"           // Always futures for optimization
                    },
                    "objective_function": "sharpe|sortino|calmar|max_drawdown"
                },
                "message": "Configuration section 'optimization' loaded successfully"
            }

            Error Response:
            {
                "status": "error",
                "section": "optimization",
                "message": "Configuration section 'optimization' not found",
                "available_sections": ["backtest", "live", "optimization"]
            }

            Shape: {
                "status": "success|error",
                "section": string,
                "config": object|undefined,
                "message": string,
                "available_sections": array[string]|undefined
            }

        Raises:
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Extracts only the "optimization" section from full configuration
            - Provides same data structure as get_config()["config"]["data"]["optimization"]
            - Settings control hyperparameter optimization execution
            - Separate from backtest settings for optimization-specific tuning

        Key Settings:
            - **cpu_cores**: Parallel processing cores (higher = faster but more resource intensive)
            - **trials**: Total parameter combinations to test (higher = more thorough but slower)
            - **best_candidates_count**: Number of top results to retain and analyze
            - **objective_function**: Metric to optimize (sharpe, sortino, calmar ratios, max_drawdown)
            - **exchange**: Optimization-specific exchange settings (often more aggressive than backtest)

        Objective Functions:
            - **"sharpe"**: Sharpe ratio (risk-adjusted returns)
            - **"sortino"**: Sortino ratio (downside deviation only)
            - **"calmar"**: Calmar ratio (annual return / max drawdown)
            - **"max_drawdown"**: Minimize maximum drawdown

        Example:
            >>> # Get optimization configuration
            >>> opt_config = get_optimization_config()
            >>> if opt_config["status"] == "success":
            ...     cores = opt_config["config"]["cpu_cores"]
            ...     trials = opt_config["config"]["trials"]
            ...     objective = opt_config["config"]["objective_function"]
            ...     print(f"Optimization: {cores} cores, {trials} trials, objective: {objective}")

            >>> # Check optimization exchange settings
            >>> opt_exchange = opt_config["config"]["exchange"]
            >>> leverage = opt_exchange["futures_leverage"]
            >>> balance = opt_exchange["balance"]
            >>> print(f"Optimization leverage: {leverage}x, balance: ${balance}")

        Performance Considerations:
            - Higher cpu_cores speeds up optimization but uses more system resources
            - More trials provides better optimization but takes longer
            - Objective function choice depends on risk tolerance and strategy goals
        """
        return get_optimization_config_service()
