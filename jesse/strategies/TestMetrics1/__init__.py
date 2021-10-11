import numpy as np

from jesse.strategies import Strategy


class TestMetrics1(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        self.buy = 10, 10
        # sell it for $50 profit
        self.take_profit = 10, 15

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def on_close_position(self, order):
        assert self.metrics['total'] == 1
        assert self.metrics['starting_balance'] == 10000
        assert self.metrics['finishing_balance'] == 10050
        assert self.metrics['win_rate'] == 1
        assert self.metrics['ratio_avg_win_loss'] is np.nan
        assert self.metrics['longs_count'] == 1
        assert self.metrics['shorts_count'] == 0
        assert self.metrics['longs_percentage'] == 100
        assert self.metrics['shorts_percentage'] == 0
        assert self.metrics['fee'] == 0
        assert self.metrics['net_profit'] == 50
        assert self.metrics['net_profit_percentage'] == 0.5
        assert self.metrics['average_win'] == 50
        assert self.metrics['average_loss'] is np.nan
        assert self.metrics['expectancy'] == 50
        assert self.metrics['expectancy_percentage'] == 0.5
        assert self.metrics['expected_net_profit_every_100_trades'] == 50
        assert self.metrics['average_holding_period'] == 300
        assert self.metrics['average_losing_holding_period'] is np.nan
        assert self.metrics['average_winning_holding_period'] == 300
        assert self.metrics['gross_loss'] == 0
        assert self.metrics['gross_profit'] == 50
        assert self.metrics['open_pl'] == 0
