def register_indicator_resources(mcp):
    
    @mcp.resource("jesse://indicator-cheatsheet")
    def indicator_cheatsheet():
        """
        Get a reference for the indicator cheatsheet.

        This reference is used to help agents use indicators in their strategies.
        It is not a complete list of all indicators, but a reference to help agents use indicators in their strategies.
        Agents should use the 'indicator_cheatsheet' tool to get a reference for the indicator cheatsheet.
        """
        return """
            Jesse Indicator Reference

            Indicators are available through:

            import jesse.indicators as ta

            Indicators commonly operate on: self.candles

            Examples:

            RSI:
            ta.rsi(self.candles)

            EMA:
            ta.ema(self.candles, period)

            SMA:
            ta.sma(self.candles, period)

            ATR:
            ta.atr(self.candles)

            ADX:
            ta.adx(self.candles)

            MACD:
            ta.macd(self.candles)

            Bollinger Bands:
            ta.bollinger_bands(self.candles)

            VWAP:
            ta.vwap(self.candles)

            Cross detection helper:

            from jesse import utils
            utils.crossed(series1, series2)

            Indicator outputs are typically series or numeric values depending on function.
            """