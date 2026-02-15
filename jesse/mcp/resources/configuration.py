"""
Jesse MCP Configuration Resources

This module provides comprehensive documentation for Jesse's configuration management
system through the MCP (Model Context Protocol). It serves as the complete reference
for all configuration-related operations, data structures, and settings.

The registered resource includes:
- Tool reference for all configuration management functions (get_config, update_config, etc.)
- Complete configuration schema documentation
- Exchange and trading pair configurations
- Backtest, live trading, and optimization settings
- Fee structures and leverage configurations
- Usage examples for configuration operations
- Best practices for configuration management

This resource is essential for understanding and managing Jesse's various
configuration options across different trading modes and environments.
"""

def register_config_resources(mcp):

    @mcp.resource("jesse://configuration")
    def configuration():
        """
        Get detailed reference for Jesse configuration management.

        This reference is used to help agents read and modify Jesse configuration settings.
        """
        return """
            # Configuration Management Reference

            This reference covers Jesse configuration management tools and data structures.

            ## Tool Reference

            ### get_config()

            Retrieves the complete Jesse configuration from the database.

            **Returns:** Complete configuration object containing all settings for backtest, live, and optimization modes.

            ### update_config()

            Saves configuration changes to the database.

            **Parameters:**
            - `config_json`: JSON string with complete configuration structure

            **Behavior:** Merges provided configuration with existing database settings.

            ### get_backtest_config()

            Retrieves backtest-specific configuration settings.

            **Returns:** Backtest configuration object with exchange settings, logging preferences, and warmup parameters.

            ### get_live_config()

            Retrieves live trading configuration settings.

            **Returns:** Live trading configuration object.

            ### get_optimization_config()

            Retrieves optimization configuration settings.

            **Returns:** Optimization configuration object with CPU cores, trial count, and objective function settings.

            ## Configuration Schema

            ### Root Structure
            ```json
            {
              "data": {
                "backtest": { /* Backtest configuration */ },
                "live": { /* Live trading configuration */ },
                "optimization": { /* Optimization configuration */ }
              }
            }
            ```

            ### Backtest Configuration
            ```json
            {
              "backtest": {
                "warm_up_candles": 240,
                "logging": {
                  "order_submission": true,
                  "trading_candles": true,
                  "shorter_period_candles": false,
                  "position_reduced": true,
                  "position_opened": true,
                  "position_closed": true,
                  "order_execution": true,
                  "position_increased": true,
                  "balance_update": true,
                  "order_cancellation": true
                },
                "exchanges": {
                  "Exchange Name": {
                    "balance": 10000,
                    "fee": 0.0004,
                    "type": "futures",
                    "futures_leverage": 1,
                    "futures_leverage_mode": "cross"
                  }
                }
              }
            }
            ```

            ### Live Configuration
            ```json
            {
              "live": {
                "warm_up_candles": 240,
                "exchanges": {
                  // Exchange configurations for live trading
                }
              }
            }
            ```

            ### Optimization Configuration
            ```json
            {
              "optimization": {
                "cpu_cores": 1,
                "best_candidates_count": 20,
                "warm_up_candles": 210,
                "trials": 200,
                "exchange": {
                  "futures_leverage": 5,
                  "fee": 0.0006,
                  "futures_leverage_mode": "cross",
                  "balance": 10000,
                  "type": "futures"
                },
                "objective_function": "sharpe"
              }
            }
            ```

            ## Usage Examples

            ### Read Complete Configuration
            ```python
            config = get_config()
            # Returns full configuration object
            ```

            ### Update Configuration
            ```python
            import json

            new_config = {
                "data": {
                    "backtest": {
                        "warm_up_candles": 300,
                        "exchanges": {
                            "Binance Spot": {
                                "balance": 50000,
                                "fee": 0.001,
                                "type": "spot"
                            }
                        }
                    }
                }
            }

            update_config(json.dumps(new_config))
            ```

            ### Get Specific Section
            ```python
            backtest_config = get_backtest_config()
            live_config = get_live_config()
            optimization_config = get_optimization_config()
            ```

            ## Configuration Persistence

            Configuration changes are applied immediately and persist in the database. Changes remain active until explicitly modified or the application is restarted.

            Configuration updates can be verified by calling `get_config()` to confirm changes have been applied.
            """