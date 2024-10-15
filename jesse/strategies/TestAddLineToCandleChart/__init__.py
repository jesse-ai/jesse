from jesse.strategies import Strategy


class TestAddLineToCandleChart(Strategy):
    def should_long(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def should_short(self):
        return False

    def after(self) -> None:
        self.add_line_to_candle_chart('test', [1, 2], 'green')
