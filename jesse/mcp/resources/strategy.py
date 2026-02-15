"""
Jesse MCP Strategy Resources

This module provides essential documentation and templates for Jesse strategy
development through the MCP (Model Context Protocol). It serves as the primary
reference for understanding how to create and structure trading strategies.

The registered resources include:

1. **Strategy Template** (`jesse://strategy-template`):
   - Complete class structure and method signatures
   - Required imports and inheritance patterns
   - Basic implementation examples for all strategy methods
   - Common patterns for entry/exit logic

2. **Execution Model** (`jesse://execution-model`):
   - Detailed explanation of strategy execution flow
   - Candle-by-candle processing order
   - When and how different methods are called
   - Order placement and position management timing

3. **Indicator Workflow** - See `jesse://indicator-workflow` resource for detailed indicator discovery and usage guidance

These resources are fundamental for creating new strategies and
understanding Jesse's strategy execution lifecycle.
"""

def register_strategy_resources(mcp):

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
