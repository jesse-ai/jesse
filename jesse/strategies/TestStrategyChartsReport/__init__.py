from jesse.strategies import Strategy


# draws every kind of strategy chart so report.strategy_charts() /
# strategy_charts_updates() have data to serve
class TestStrategyChartsReport(Strategy):
    def should_long(self):
        return False

    def should_short(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def update_chart(self):
        self.add_line_to_candle_chart('ema', float(self.close), 'blue')
        self.add_horizontal_line_to_candle_chart('level', 10.0, 'red')
        self.add_extra_line_chart('RSI', 'rsi', 50.0, 'green')
        self.add_horizontal_line_to_extra_chart('RSI', 'oversold', 30.0, 'gray')
