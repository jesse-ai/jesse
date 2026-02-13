def register_position_resources(mcp):
    @mcp.resource("jesse://position-sizing")
    def position_sizing():
        """
        Get a reference for the position sizing.

        This reference is used to help agents size their positions.
        
        """
        return """
            Position Sizing Reference

            Helpers are available in jesse.utils.

            Fractional sizing example:

            qty = utils.size_to_qty(
                self.available_margin * fraction,
                self.price,
                fee_rate=self.fee_rate
            )

            Risk-based sizing example:

            qty = utils.risk_to_qty(
                available_margin,
                risk_percent,
                entry_price,
                stop_price,
                fee_rate=self.fee_rate
            )

            Sizing is typically derived from:

            - available margin
            - entry price
            - stop distance
            - fee rate
            """
            
    @mcp.resource("jesse://risk-management")
    def risk_management():
        """
        Get a reference for the risk management.

        This reference is used to help agents manage their risks.
        It is not a complete list of all risk management methods, but a reference to help agents use risk management in their strategies.
        Agents should use the 'risk_management' tool to get a reference for the risk management.
        """
        return """
            Risk Management Reference Patterns

            Exit handling is often implemented using:

            - stop_loss
            - take_profit
            - update_position logic

            ATR-based example:

            atr = ta.atr(self.candles)

            stop_price = entry_price - atr * 2
            target_price = entry_price + atr * 3

            Percentage-based example:

            Long position:

            stop_price = entry * 0.99
            target_price = entry * 1.02

            Short position uses inverted percentages.

            Exit checks can be placed inside update_position().
            """