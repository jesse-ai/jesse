def register_backtest_management_resources(mcp):

    @mcp.resource("jesse://backtest-management")
    def backtest_management():
        """
        Get detailed reference for backtest creation and management tools.

        This reference provides comprehensive documentation for backtest operations in Jesse.
        """
        return """
            # Backtest Management Reference

            This reference covers the complete set of tools for creating, managing, and running backtests with Jesse.

            ## Tool Reference

            ### create_backtest_draft()

            Creates a new backtest session draft with specified parameters.

            Parameters:
            - `exchange` (optional): Exchange name (default: "Binance Perpetual Futures")
            - `routes`: JSON string array of route configurations
            - `data_routes` (optional): JSON string array of data route configurations
            - `start_date` (optional): Backtest start date (default: "2024-01-01")
            - `finish_date` (optional): Backtest end date (default: "2024-03-01")
            - Additional options: debug_mode, export_csv, export_json, export_chart, fast_mode, benchmark

            Default Configuration:
            ```json
            {
              "exchange": "Binance Perpetual Futures",
              "routes": "[{\\"exchange\\": \\"Binance Perpetual Futures\\", \\"strategy\\": \\"ExampleStrategy\\", \\"symbol\\": \\"BTC-USDT\\", \\"timeframe\\": \\"4h\\"}]",
              "data_routes": "[]",
              "start_date": "2024-01-01",
              "finish_date": "2024-03-01",
              "debug_mode": false,
              "export_csv": false,
              "export_json": false,
              "export_chart": true,
              "export_tradingview": false,
              "fast_mode": false,
              "benchmark": true
            }
            ```

            Returns: Session ID (UUID format) and configuration object

            ### update_backtest_draft()

            Updates an existing backtest draft configuration.

            Parameters:
            - `backtest_id`: UUID of the backtest session to update (required)
            - `state`: JSON string with complete state object

            State Parameter Format:
            The state parameter must contain only the inner state object:

            ```json
            {
              "form": {
                "exchange": "Binance Perpetual Futures",
                "routes": [...],
                "start_date": "2024-01-01",
                "finish_date": "2024-03-01"
              },
              "results": {
                "showResults": false,
                "executing": false
              }
            }
            ```

            Update Process:
            1. Retrieve current state with `get_backtest_session()`
            2. Extract state object: `response.session.state.state`
            3. Merge changes with current state
            4. Call `update_backtest_draft()` with merged state

            ### get_backtest_session()

            Retrieves details of a specific backtest session.

            Parameters:
            - `session_id`: UUID of the backtest session

            Returns:
            ```json
            {
              "status": "success",
              "session": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "state": {
                  "form": { /* Configuration */ },
                  "results": { /* Results */ }
                },
                "metrics": { /* Performance metrics */ },
                "trades": [ /* Trade history */ ]
              }
            }
            ```

            ### get_backtest_sessions()

            Lists backtest sessions with pagination and filtering.

            Parameters:
            - `limit` (optional): Maximum sessions to return (default: 50)
            - `offset` (optional): Skip N sessions for pagination (default: 0)
            - `title_search` (optional): Search in session titles
            - `status_filter` (optional): Filter by status ("finished", "running", "cancelled")
            - `date_filter` (optional): Filter by date ("today", "this_week", "this_month")

            Returns: Array of session objects sorted by most recently updated

            ### run_backtest()

            Executes a backtest using provided configuration.

            Parameters:
            - `session_id`: UUID of the backtest session to run
            - `config`: Configuration object from `get_backtest_config()['config']`
            - `timeout_seconds` (optional): Maximum wait time (default: 24 hours)

            Process:
            1. Parses configuration and merges with session form data
            2. Validates against BacktestRequestJson model
            3. Starts backtest execution
            4. Monitors progress via WebSocket events

            Returns: Success message with metrics or error details

            ### cancel_backtest()

            Cancels a running backtest process.

            Parameters:
            - `session_id`: UUID of the backtest to cancel

            Returns: Updated session status

            ### purge_backtest_sessions()

            Deletes old backtest sessions from database.

            Parameters:
            - `days_old` (optional): Age threshold in days (null deletes all sessions)

            Returns: Number of deleted sessions

            ## Usage Examples

            ### Basic Backtest Creation
            ```python
            draft = create_backtest_draft(
                routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}]',
                start_date="2024-01-01",
                finish_date="2024-12-31"
            )
            # Returns: { backtest_id: "550e8400-e29b-41d4-a716-446655440000" }
            ```

            ### Configuration Override
            ```python
            draft = create_backtest_draft(
                exchange="Binance Spot",
                routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "ETH-USDT", "timeframe": "4h"}]',
                data_routes='[{"exchange": "Binance Spot", "symbol": "ETH-USDT", "timeframe": "4h"}]',
                debug_mode=true
            )
            ```

            ### Multiple Strategies
            ```python
            routes = '''[
              {"exchange": "Binance Spot", "strategy": "Strategy1", "symbol": "BTC-USDT", "timeframe": "1h"},
              {"exchange": "Binance Spot", "strategy": "Strategy2", "symbol": "ETH-USDT", "timeframe": "4h"}
            ]'''

            draft = create_backtest_draft(routes=routes)
            ```

            ### State Updates

            Appending Routes:
            ```python
            session = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
            current_state = session.session.state.state
            new_route = {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "DOGE-USDT", "timeframe": "1h"}
            updated_routes = current_state.form.routes + [new_route]
            merged_state = current_state.copy()
            merged_state.form.routes = updated_routes
            update_backtest_draft("550e8400-e29b-41d4-a716-446655440000", merged_state)
            ```

            Field Updates:
            ```python
            session = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
            current_state = session.session.state.state
            merged_state = current_state.copy()
            merged_state.form.start_date = "2024-06-01"
            merged_state.form.debug_mode = true
            update_backtest_draft("550e8400-e29b-41d4-a716-446655440000", merged_state)
            ```

            ### Running Backtests
            ```python
            # Get configuration
            config = get_backtest_config()

            # Execute backtest
            result = run_backtest("550e8400-e29b-41d4-a716-446655440000", config['config'])

            # Check results
            session_details = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
            ```

            ## Route Configuration Schema

            Route Object:
            ```json
            {
              "exchange": "string (exchange name)",
              "strategy": "string (strategy class name)",
              "symbol": "string (trading pair)",
              "timeframe": "string (1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1D, 3D, 1W, 1M)"
            }
            ```

            Data Route Object:
            ```json
            {
              "exchange": "string (exchange name)",
              "symbol": "string (trading pair)",
              "timeframe": "string (timeframe)"
            }
            ```

            ## Error Handling

            Common error scenarios and recovery:

            - Invalid Routes: Check for unique exchange-symbol pairs
            - Missing Data: Import candle data before backtesting
            - Configuration Errors: Check JSON structure
            - Timeout Issues: Adjust timeout_seconds parameter
            - State Conflicts: Retrieve current state before updates

            ## Best Practices

            debug_mode can assist during development
            Charts and JSON exports support analysis
            Resource usage monitoring helps with large backtests
            Regular archiving of completed sessions improves management
            """