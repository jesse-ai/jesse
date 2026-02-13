def register_backtest_resources(mcp):
    
    @mcp.resource("jesse://metrics-guide")
    def metrics_guide():
        """
        Get a reference for the backtest metrics.

        This reference is used to help agents understand the backtest metrics.
        It is not a complete list of all backtest metrics, but a reference to help agents use backtest metrics in their strategies.
        Agents should use the 'metrics_guide' tool to get a reference for the backtest metrics.
        """
        return """
            Backtest Metrics Reference

            Common metrics returned from Jesse backtests:

            Net Profit:
            Total return over the test period.

            Sharpe Ratio:
            Risk-adjusted return measure.

            Max Drawdown:
            Largest equity decline from peak.

            Win Rate:
            Percentage of winning trades.

            Profit Factor:
            Gross profit divided by gross loss.

            Metrics are often compared together when evaluating strategy changes.
            """