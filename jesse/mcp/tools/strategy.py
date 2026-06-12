"""
Jesse Strategy Management Tools

This module provides MCP tools for managing Jesse trading strategies,
using the strategy controller endpoints like the dashboard does.

The tools include:
- create_strategy: Creates a new strategy with basic template code
- read_strategy: Reads the content of an existing strategy using Jesse's API
- write_strategy: Updates the content of an existing strategy using Jesse's API

All tools require authentication via Jesse admin password.
"""

from .services import (
    create_strategy_service,
    read_strategy_service,
    write_strategy_service
)


def register_strategy_tools(mcp):
    """
    Register the tools for the strategy related operations.

    This module provides MCP tools for managing Jesse trading strategies:
    - create_strategy: Creates a new strategy with basic template code
    - read_strategy: Reads the content of an existing strategy using Jesse's API
    - write_strategy: Updates the content of an existing strategy using Jesse's API

    All tools require authentication via Jesse admin password.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def create_strategy(name: str, content: str) -> dict:
        """
        Create a new trading strategy with custom content in Jesse.

        Creates a new strategy file and immediately populates it with the provided
        Python code content. This streamlined approach allows creating complete,
        functional strategies in a single operation rather than requiring separate
        create and write operations.

        The provided content must be valid Python code following Jesse's Strategy
        class structure with proper imports and method implementations.

        Parameters:
            name (str): Name for the new strategy class and file
                Requirements: Valid Python identifier, no spaces, unique within Jesse
                Examples: "MyStrategy", "RSIStrategy", "MeanReversionStrategy"
                Shape: String matching Python class naming conventions
            content (str): Complete Python code for the strategy implementation
                Must include proper imports, class definition, and all required methods
                Must be valid Python syntax following Jesse Strategy structure
                Shape: Multi-line string containing complete strategy code

        Returns:
            dict: Creation and population result with status and metadata:

            Success Response:
            {
                "status": "success",
                "action": "strategy_created_and_populated",
                "strategy_name": "RSIStrategy",
                "message": "Strategy 'RSIStrategy' created and populated successfully",
                "path": "/path/to/strategies/RSIStrategy.py"
            }

            Error Response - Strategy Exists:
            {
                "status": "error",
                "action": "strategy_creation_failed",
                "strategy_name": "RSIStrategy",
                "error_type": "strategy_exists",
                "message": "Strategy 'RSIStrategy' already exists"
            }

            Error Response - Content Write Failed:
            {
                "status": "error",
                "action": "strategy_population_failed",
                "strategy_name": "RSIStrategy",
                "error_type": "write_failed",
                "message": "Strategy created but content write failed",
                "creation_success": true,
                "write_error": "detailed write error"
            }

            Error Response - Authentication:
            {
                "status": "error",
                "action": "strategy_creation_failed",
                "strategy_name": "RSIStrategy",
                "error_type": "authentication_failed",
                "message": "Invalid password provided"
            }

            Error Response - Connection:
            {
                "status": "error",
                "action": "strategy_creation_failed",
                "strategy_name": "RSIStrategy",
                "error_type": "connection_error",
                "message": "Could not connect to Jesse API",
                "details": "Connection timeout details"
            }

            Shape: {
                "status": "success|error",
                "action": "strategy_created_and_populated|strategy_creation_failed|strategy_population_failed",
                "strategy_name": string,
                "message": string,
                "path": string|undefined,
                "error_type": string|undefined,
                "details": string|undefined,
                "creation_success": bool|undefined,
                "write_error": string|undefined
            }

        Raises:
            ValueError: If Jesse configuration is invalid
            ConnectionError: If Jesse API is unreachable

        Content Requirements:
            - Must import Strategy: `from jesse.strategies import Strategy`
            - Must import indicators: `import jesse.indicators as ta`
            - Must import utilities: `from jesse import utils`
            - Class must inherit from Strategy and match the name parameter
            - Must implement required methods (should_long, should_short, etc.)
            - Code must be syntactically valid Python

        Required Methods:
            - `should_long() -> bool` - Entry condition for long positions
            - `should_short() -> bool` - Entry condition for short positions
            - `go_long()` - Place long entry order
            - `go_short()` - Place short entry order
            - `should_cancel_entry() -> bool` - Cancel pending entries
            - `update_position()` - Manage open positions and exits

        Strategy Execution Model:
            - Runs once per candle in the sequence: before() → entry logic → after()
            - Entry signals in should_long/should_short methods
            - Order placement in go_long/go_short methods
            - Position management in update_position method
            - Exit logic via liquidation, stop_loss, or take_profit

        Usage Workflow:
            1. Prepare complete strategy code with logic and indicators
            2. create_strategy(name, content) → create file and populate in one step
            3. Use in backtesting with routes configuration
            4. Iterate: read_strategy() → modify → write_strategy() for updates

        Example:
            >>> # Create a complete RSI strategy in one step
            >>> strategy_code = '''
            ... from jesse.strategies import Strategy
            ... import jesse.indicators as ta
            ... from jesse import utils
            ...
            ... class RSIStrategy(Strategy):
            ...     def should_long(self) -> bool:
            ...         rsi = ta.rsi(self.candles, period=14)
            ...         return rsi < 30
            ...
            ...     def should_short(self) -> bool:
            ...         rsi = ta.rsi(self.candles, period=14)
            ...         return rsi > 70
            ...
            ...     def go_long(self):
            ...         qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
            ...         self.buy = qty, self.price
            ...
            ...     def go_short(self):
            ...         qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
            ...         self.sell = qty, self.price
            ...
            ...     def should_cancel_entry(self) -> bool:
            ...         return False
            ...
            ...     def update_position(self):
            ...         rsi = ta.rsi(self.candles, period=14)
            ...         if self.is_long and rsi > 50:
            ...             self.liquidate()
            ...         elif self.is_short and rsi < 50:
            ...             self.liquidate()
            ... '''
            >>>
            >>> result = create_strategy("RSIStrategy", strategy_code)
            >>> if result["status"] == "success":
            ...     print(f"✅ Complete strategy created: {result['strategy_name']}")
            ...     print(f"📁 Location: {result['path']}")
            ... else:
            ...     print(f"❌ Creation failed: {result['message']}")

            >>> # Handle partial failure (creation succeeded but write failed)
            >>> if result.get("creation_success") and result["status"] == "error":
            ...     print("Strategy file created but content write failed")
            ...     # Could retry with write_strategy() or fix content and try again
            ...     fixed_result = create_strategy("RSIStrategy", fixed_code)

        Best Practices:
            - Test strategy logic with sample data before creating
            - Use indicator tools to verify correct indicator usage
            - Include proper error handling in strategy methods
            - Add comments explaining the trading logic
            - Use meaningful variable names and follow Python conventions
            - Implement position sizing based on available margin
            - Test with small position sizes initially

        Integration:
            After creation, the strategy is immediately available for:
            - Backtesting with run_backtest()
            - Configuration in backtest drafts
            - Further modification with write_strategy()
        """
        # First create the strategy file
        create_result = create_strategy_service(name)

        if create_result["status"] != "success":
            return create_result

        # Then populate it with content
        write_result = write_strategy_service(name, content)

        if write_result["status"] == "success":
            # Both operations succeeded
            return {
                "status": "success",
                "action": "strategy_created_and_populated",
                "strategy_name": name,
                "message": f"Strategy '{name}' created and populated successfully",
                "path": create_result.get("path")
            }
        else:
            # Creation succeeded but write failed
            return {
                "status": "error",
                "action": "strategy_population_failed",
                "strategy_name": name,
                "error_type": "write_failed",
                "message": "Strategy created but content write failed",
                "creation_success": True,
                "write_error": write_result.get("message", "Unknown write error"),
                "path": create_result.get("path")
            }

    
    @mcp.tool()
    def read_strategy(name: str) -> dict:
        """
        Retrieve the complete source code of a Jesse trading strategy.

        Reads the Python code content of an existing strategy file through Jesse's API.
        This provides access to the current implementation including all methods,
        indicators, logic, and comments. Essential for reviewing, modifying, or
        understanding existing strategies.

        Use after create_strategy() to see the template, or to examine existing
        strategies before modification with write_strategy().

        Parameters:
            name (str): Exact name of the strategy to read (case-sensitive)
                Must match the class name and filename exactly
                Examples: "MyStrategy", "RSIStrategy"
                Shape: String matching existing strategy name

        Returns:
            dict: Strategy content with metadata:

            Success Response:
            {
                "status": "success",
                "action": "strategy_read",
                "strategy_name": "RSIStrategy",
                "message": "Strategy 'RSIStrategy' content read successfully",
                "content": "from jesse.strategies import Strategy\\nimport jesse.indicators as ta\\nfrom jesse import utils\\n\\nclass RSIStrategy(Strategy):\\n    def should_long(self) -> bool:\\n        return False\\n    # ... full strategy code"
            }

            Error Response - Not Found:
            {
                "status": "error",
                "action": "strategy_read_failed",
                "strategy_name": "NonExistentStrategy",
                "error_type": "strategy_not_found",
                "message": "Strategy 'NonExistentStrategy' not found"
            }

            Error Response - Authentication:
            {
                "status": "error",
                "action": "strategy_read_failed",
                "strategy_name": "MyStrategy",
                "error_type": "authentication_failed",
                "message": "Invalid password provided"
            }

            Error Response - Connection:
            {
                "status": "error",
                "action": "strategy_read_failed",
                "strategy_name": "MyStrategy",
                "error_type": "connection_error",
                "message": "Could not connect to Jesse API",
                "details": "Connection timeout details"
            }

            Shape: {
                "status": "success|error",
                "action": "strategy_read|strategy_read_failed",
                "strategy_name": string,
                "message": string,
                "content": string|undefined,
                "error_type": string|undefined,
                "details": string|undefined
            }

        Raises:
            ValueError: If Jesse configuration is invalid
            ConnectionError: If Jesse API is unreachable

        Content Structure:
            The returned content includes:
            - Import statements (Strategy, ta, utils)
            - Class definition inheriting from Strategy
            - All implemented methods:
                * should_long() / should_short() - entry conditions
                * go_long() / go_short() - order placement
                * should_cancel_entry() - entry cancellation logic
                * update_position() - position management
                * before() / after() - candle processing hooks
            - Indicator usage and calculations
            - Position sizing logic
            - Risk management rules

        Usage Patterns:
            - Review strategy logic before backtesting
            - Examine existing strategies for learning
            - Prepare code for modification with write_strategy()
            - Debug strategy behavior by reading current state

        Example:
            >>> # Read a newly created strategy
            >>> result = read_strategy("MyStrategy")
            >>> if result["status"] == "success":
            ...     code = result["content"]
            ...     print("Strategy code retrieved successfully")
            ...     # Count lines of code
            ...     lines = len(code.split('\\n'))
            ...     print(f"Strategy has {lines} lines of code")
            ... else:
            ...     print(f"Failed to read strategy: {result['message']}")

            >>> # Handle missing strategy
            >>> result = read_strategy("NonExistentStrategy")
            >>> if result["error_type"] == "strategy_not_found":
            ...     print("Strategy doesn't exist - create it first")
            ...     create_result = create_strategy("NonExistentStrategy")

            >>> # Read strategy for modification
            >>> current = read_strategy("RSIStrategy")
            >>> if current["status"] == "success":
            ...     # Modify the code (add RSI logic, etc.)
            ...     modified_code = current["content"].replace(
            ...         "def should_long(self) -> bool:\\n        return False",
            ...         "def should_long(self) -> bool:\\n        rsi = ta.rsi(self.candles, period=14)\\n        return rsi < 30"
            ...     )
            ...     # Write back the modified strategy
            ...     write_strategy("RSIStrategy", modified_code)

        Integration with Development:
            - Use with indicator tools to understand indicator usage
            - Combine with backtest tools for testing changes
            - Review before deployment to live trading
            - Archive important versions by reading and saving externally
        """
        return read_strategy_service(name)
    
    @mcp.tool()
    def write_strategy(name: str, content: str) -> dict:
        """
        Update the source code of a Jesse trading strategy.

        Saves modified Python code to an existing strategy file through Jesse's API.
        This is the primary method for implementing trading logic, adding indicators,
        and customizing strategy behavior. The content must be valid Python code
        following Jesse's Strategy class structure.

        Use read_strategy() first to get current content, modify it, then save
        with this function. Changes take effect immediately for new backtests.

        Parameters:
            name (str): Exact name of the strategy to update (case-sensitive)
                Must match existing strategy name exactly
                Examples: "MyStrategy", "RSIStrategy"
                Shape: String matching existing strategy name
            content (str): Complete Python code for the strategy
                Must include proper class definition, imports, and methods
                Must be valid Python syntax and follow Jesse Strategy structure
                Shape: Multi-line string containing complete strategy code

        Returns:
            dict: Update result with confirmation:

            Success Response:
            {
                "status": "success",
                "action": "strategy_updated",
                "strategy_name": "RSIStrategy",
                "message": "Strategy 'RSIStrategy' content updated successfully"
            }

            Error Response - Not Found:
            {
                "status": "error",
                "action": "strategy_write_failed",
                "strategy_name": "NonExistentStrategy",
                "error_type": "strategy_not_found",
                "message": "Strategy 'NonExistentStrategy' not found"
            }

            Error Response - Authentication:
            {
                "status": "error",
                "action": "strategy_write_failed",
                "strategy_name": "MyStrategy",
                "error_type": "authentication_failed",
                "message": "Invalid password provided"
            }

            Error Response - Connection:
            {
                "status": "error",
                "action": "strategy_write_failed",
                "strategy_name": "MyStrategy",
                "error_type": "connection_error",
                "message": "Could not connect to Jesse API",
                "details": "Connection timeout details"
            }

            Shape: {
                "status": "success|error",
                "action": "strategy_updated|strategy_write_failed",
                "strategy_name": string,
                "message": string,
                "error_type": string|undefined,
                "details": string|undefined
            }

        Raises:
            ValueError: If Jesse configuration is invalid
            ConnectionError: If Jesse API is unreachable

        Code Requirements:
            - Must import Strategy: `from jesse.strategies import Strategy`
            - Must import indicators: `import jesse.indicators as ta`
            - Must import utilities: `from jesse import utils`
            - Class must inherit from Strategy
            - Must implement required methods (should_long, should_short, etc.)
            - Code must be syntactically valid Python
            - Strategy name in code must match the file/class name

        Required Methods:
            - `should_long() -> bool` - Entry condition for long positions
            - `should_short() -> bool` - Entry condition for short positions
            - `go_long()` - Place long entry order
            - `go_short()` - Place short entry order
            - `should_cancel_entry() -> bool` - Cancel pending entries
            - `update_position()` - Manage open positions and exits

        Optional Methods:
            - `before()` - Pre-candle processing
            - `after()` - Post-candle processing
            - Custom helper methods

        Development Workflow:
            1. create_strategy() or read_strategy() → get starting code
            2. Modify code with indicators, logic, risk management
            3. write_strategy() → save changes
            4. run_backtest() → test the strategy
            5. Iterate: read → modify → write → test

        Example:
            >>> # Basic strategy implementation
            >>> strategy_code = '''
            ... from jesse.strategies import Strategy
            ... import jesse.indicators as ta
            ... from jesse import utils
            ...
            ... class SimpleRSIStrategy(Strategy):
            ...     def should_long(self) -> bool:
            ...         rsi = ta.rsi(self.candles, period=14)
            ...         return rsi < 30
            ...
            ...     def should_short(self) -> bool:
            ...         rsi = ta.rsi(self.candles, period=14)
            ...         return rsi > 70
            ...
            ...     def go_long(self):
            ...         qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
            ...         self.buy = qty, self.price
            ...
            ...     def go_short(self):
            ...         qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
            ...         self.sell = qty, self.price
            ...
            ...     def should_cancel_entry(self) -> bool:
            ...         return False
            ...
            ...     def update_position(self):
            ...         # Close position if RSI reaches midline
            ...         rsi = ta.rsi(self.candles, period=14)
            ...         if self.is_long and rsi > 50:
            ...             self.liquidate()
            ...         elif self.is_short and rsi < 50:
            ...             self.liquidate()
            ... '''
            >>>
            >>> result = write_strategy("SimpleRSIStrategy", strategy_code)
            >>> if result["status"] == "success":
            ...     print("✅ Strategy updated successfully")
            ... else:
            ...     print(f"❌ Update failed: {result['message']}")

            >>> # Read-modify-write pattern
            >>> current = read_strategy("MyStrategy")
            >>> if current["status"] == "success":
            ...     modified_code = current["content"].replace(
            ...         "return False",  # in should_long
            ...         "return ta.crossover(ta.sma(self.candles, 10), ta.sma(self.candles, 20))"
            ...     )
            ...     write_strategy("MyStrategy", modified_code)

        Best Practices:
            - Always test syntax before saving (Jesse will validate on write)
            - Use meaningful variable names and comments
            - Implement proper error handling
            - Test with small position sizes first
            - Document indicator parameters and logic
            - Version control important strategy changes

        Validation:
            Jesse validates code syntax and structure on save
            Invalid code will be rejected with specific error messages
            Use indicator tools to ensure correct indicator usage
        """
        return write_strategy_service(name, content)