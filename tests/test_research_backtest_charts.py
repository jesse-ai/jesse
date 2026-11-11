import numpy as np
import pytest

import jesse.helpers as jh
from jesse.research import backtest
from jesse.services import charts
from jesse.strategies import Strategy


class _BuyEveryCandle(Strategy):
    def should_long(self):
        return True

    def go_long(self):
        self.buy = 1, self.price

    def update_position(self):
        self.liquidate()

    def should_cancel_entry(self):
        return True


def _run():
    n = 120
    start = jh.date_to_timestamp('2024-01-01')
    close = 100 + np.sin(np.arange(n) / 5)
    c = np.zeros((n, 6))
    c[:, 0] = start + np.arange(n) * 60_000
    c[:, 1] = np.r_[close[0], close[:-1]]
    c[:, 2] = close
    c[:, 3] = np.maximum(c[:, 1], close)
    c[:, 4] = np.minimum(c[:, 1], close)
    c[:, 5] = 1
    config = {'starting_balance': 10_000, 'fee': 0, 'type': 'spot', 'futures_leverage': 1,
              'futures_leverage_mode': 'cross', 'exchange': 'Binance Spot', 'warm_up_candles': 0}
    routes = [{'exchange': 'Binance Spot', 'strategy': _BuyEveryCandle, 'symbol': 'BTC-USDT', 'timeframe': '1m'}]
    candles = {jh.key('Binance Spot', 'BTC-USDT'): {'exchange': 'Binance Spot', 'symbol': 'BTC-USDT', 'candles': c}}
    return backtest(config, routes, [], candles, generate_charts=True)


def test_a_chart_failure_still_returns_the_finished_backtest(monkeypatch):
    def fail(**kwargs):
        raise MemoryError('Unable to allocate 165. GiB for an array')

    monkeypatch.setattr(charts, '_plot_backtest_charts', fail)

    with pytest.warns(UserWarning, match='MemoryError'):
        result = _run()

    assert result['metrics']['total'] > 0
    assert 'charts_session_id' not in result
