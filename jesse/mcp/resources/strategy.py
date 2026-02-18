"""
Jesse MCP Strategy Resources

This module provides essential documentation and templates for Jesse strategy
development through the MCP (Model Context Protocol). It serves as the primary
reference for understanding how to create and structure trading strategies.

The registered resources include:

1. **Strategy Development Issues** (`jesse://strategy-development-issues`):
   - Common pitfalls and errors during strategy development
   - Proven solutions for frequently encountered problems
   - Spot vs futures trading differences
   - Multi-timeframe strategy limitations
   - Debugging workflow and best practices

2. **Strategy Template** (`jesse://strategy-template`):
   - Complete class structure and method signatures
   - Required imports and inheritance patterns
   - Basic implementation examples for all strategy methods
   - Common patterns for entry/exit logic

3. **Execution Model** (`jesse://execution-model`):
   - Detailed explanation of strategy execution flow
   - Candle-by-candle processing order
   - When and how different methods are called
   - Order placement and position management timing

4. **Indicator Workflow** - See `jesse://indicator-workflow` resource for detailed indicator discovery and usage guidance

These resources are fundamental for creating new strategies and
understanding Jesse's strategy execution lifecycle.
"""

def register_strategy_resources(mcp):

    @mcp.resource("jesse://strategy-development-issues")
    def strategy_development_issues():
        """
        CRITICAL TROUBLESHOOTING GUIDE: Common strategy development issues and solutions.

        This is the primary reference for debugging strategy code errors. Always consult this
        resource first when encountering issues during strategy writing or backtesting.

        Covers: multi-timeframe limitations, spot vs futures trading, position sizing,
        indicator usage, and common error patterns with proven solutions.
        """
        return """
            Jesse Strategy Development Issues & Solutions

            This reference covers common pitfalls and their solutions encountered during
            strategy development, based on real development experiences.

            == COMMON ISSUES & SOLUTIONS ==

            === 1. Multi-Timeframe Data Access ===

            PROBLEM: Attempting to access higher timeframe data within strategy logic
            ```
            # WRONG - This doesn't work as expected
            candles_4h = self.get_candles('4h')
            candles_1h = self.get_candles('1h')
            ```

            SOLUTION: Jesse strategies run on a single timeframe. For multi-timeframe strategies:
            - Create separate backtests for each timeframe
            - Use the primary timeframe for execution
            - Access indicators from the strategy's assigned timeframe only

            CORRECT APPROACH: Run separate backtests for different timeframes
            ```
            # Backtest 1: 4h timeframe strategy
            {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}

            # Backtest 2: 1h timeframe strategy
            {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}
            ```

            === 2. Balance vs Capital Confusion ===

            PROBLEM: Using deprecated 'self.capital' instead of 'self.balance'
            ```
            # WRONG
            qty = utils.size_to_qty(self.capital * 0.1, self.close, fee_rate=self.fee_rate)
            # ERROR: AttributeError: 'Strategy' object has no attribute 'capital'
            ```

            SOLUTION: Use 'self.balance' for current account balance
            ```
            # CORRECT
            qty = utils.size_to_qty(self.balance * 0.1, self.close, fee_rate=self.fee_rate)
            ```

            === 3. Spot Trading Exit Management ===

            PROBLEM: Setting stop_loss/take_profit in go_long() for spot trading
            ```
            # WRONG - Works for futures, fails for spot
            def go_long(self):
                self.buy = qty, self.close
                self.stop_loss = self.close * 0.95  # 5% stop loss
                self.take_profit = self.close * 1.10  # 10% take profit
            # ERROR: Setting self.take_profit in go_long() not supported for spot trading
            ```

            SOLUTION: Use update_position() for spot trading exits
            ```
            # CORRECT - For spot trading
            def go_long(self):
                qty = utils.size_to_qty(self.balance * 0.1, self.close, fee_rate=self.fee_rate)
                self.buy = qty, self.close

            def on_open_position(self, order):
                self.entry_price = self.position.entry_price

            def update_position(self):
                if self.is_long:
                    # Check stop loss
                    if self.close <= self.entry_price * 0.95:
                        self.liquidate()
                        return
                    # Check take profit
                    if self.close >= self.entry_price * 1.10:
                        self.liquidate()
                        return
            ```

            === 4. Futures vs Spot Trading Differences ===

            PROBLEM: Using futures-style exit logic for spot trading

            FUTURES TRADING (allows stop_loss/take_profit in go_long):
            ```
            def go_long(self):
                self.buy = qty, self.price
                self.stop_loss = self.price * 0.95    # ✓ Works for futures
                self.take_profit = self.price * 1.10  # ✓ Works for futures
            ```

            SPOT TRADING (requires update_position):
            ```
            def go_long(self):
                self.buy = qty, self.close  # Note: use self.close, not self.price

            def update_position(self):
                if self.is_long:
                    if self.close <= self.entry_price * 0.95:
                        self.liquidate()
                    elif self.close >= self.entry_price * 1.10:
                        self.liquidate()
            ```

            === 5. Indicator Data Requirements ===

            PROBLEM: Not ensuring sufficient candle data for indicators
            ```
            # WRONG - May fail if insufficient candles
            def should_long(self):
                rsi = ta.rsi(self.candles, 14)
                return rsi < 30
            ```

            SOLUTION: Check candle count before using indicators
            ```
            # CORRECT
            def should_long(self):
                if len(self.candles) < 14:  # RSI period
                    return False
                rsi = ta.rsi(self.candles, 14)
                return rsi < 30
            ```

            For multiple indicators, use max() to ensure all have enough data:
            ```
            required_candles = max(self.rsi_period, self.bb_period, self.slow_ma_period)
            if len(self.candles) < required_candles:
                return False
            ```

            === 6. Backtest Configuration Issues ===

            PROBLEM: Multiple routes with same exchange-symbol pair
            ```
            # WRONG - Causes InvalidRoutes error
            "routes": [
                {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"},
                {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}
            ]
            # ERROR: each exchange-symbol pair can be traded only once
            ```

            SOLUTION: Run separate backtests for different timeframes
            ```
            # CORRECT - Separate backtests
            # Backtest 1: 1h timeframe
            "routes": [
                {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "1h"}
            ]

            # Backtest 2: 4h timeframe
            "routes": [
                {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}
            ]
            ```

            === 7. Position Sizing Errors ===

            PROBLEM: Using fixed quantities instead of dynamic sizing
            ```
            # WRONG - Fixed quantity regardless of capital
            def go_long(self):
                self.buy = 100, self.close  # Always buys 100 units
            ```

            SOLUTION: Use dynamic position sizing based on available capital
            ```
            # CORRECT - Size based on capital percentage
            def go_long(self):
                risk_amount = self.balance * 0.05  # 5% of balance
                qty = utils.size_to_qty(risk_amount, self.close, fee_rate=self.fee_rate)
                self.buy = qty, self.close
            ```

            === DEBUGGING WORKFLOW ===

            When encountering errors:

            1. Check the error message carefully - Jesse provides specific error descriptions
            2. Verify you're using the correct attributes (balance vs capital, close vs price)
            3. Ensure proper method usage for spot vs futures trading
            4. Confirm sufficient candle data for all indicators
            5. Test with simplified logic first, then add complexity

            === TESTING BEST PRACTICES ===

            - Start with simple RSI-only strategy to verify basic functionality
            - Test position sizing separately from entry logic
            - Use conservative position sizes (5-10% of capital) during development
            - Verify exit logic works before optimizing entry conditions
            - Run backtests on short time periods first to catch errors quickly

            === COMMON ERROR MESSAGES ===

            "Setting self.take_profit in go_long() not supported for spot trading"
            → Use update_position() for spot trading exits

            "Strategy.get_candles() missing required positional argument"
            → Strategies work on single timeframe; use separate backtests for multi-timeframe

            "'Strategy' object has no attribute 'capital'"
            → Use self.balance instead of self.capital

            "InvalidRoutes: each exchange-symbol pair can be traded only once"
            → Run separate backtests for different timeframes of same symbol
            """

    @mcp.resource("jesse://strategy-template")
    def strategy_template():
        """
        Get a reference for the strategy template.
        This reference is used to help agents create a new strategy.
        
        """
        return """
            Jesse Strategy Template Reference

            Strategies inherit from Strategy and define entry and exit logic.

            Common structure:

            from jesse.strategies import Strategy
            import jesse.indicators as ta
            from jesse import utils


            class MyStrategy(Strategy):

                def should_long(self) -> bool:
                    return False

                def should_short(self) -> bool:
                    return False

                def go_long(self):
                    qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
                    self.buy = qty, self.price

                def go_short(self):
                    qty = utils.size_to_qty(self.available_margin * 0.1, self.price, fee_rate=self.fee_rate)
                    self.sell = qty, self.price

                def should_cancel_entry(self) -> bool:
                    return False

                def update_position(self):
                    pass

            Typical methods used in strategies:

            - should_long
            - should_short
            - go_long
            - go_short
            - should_cancel_entry
            - update_position
            """
            
    @mcp.resource("jesse://execution-model")
    def execution_model():
        """
        Get a reference for the execution model.

        This reference is used to help agents understand the execution model of the strategy.
        It is not a complete list of all execution model methods, but a reference to help agents use execution model in their strategies.
        Agents should use the 'execution_model' tool to get a reference for the execution model.
        """
        return """
            Jesse Strategy Execution Model

            Strategy logic runs once per candle.

            Typical flow:

            before()

            If a position is open:
                update_position()

            If no open position:

                If entry orders exist:
                    should_cancel_entry()

                Otherwise:
                    should_long → go_long
                    should_short → go_short

            after()

            Entries are placed in go_long / go_short.
            Exit logic is handled through stop_loss, take_profit, or update_position.
            """
