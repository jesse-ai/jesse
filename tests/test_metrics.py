from jesse.store import store
from jesse.testing_utils import single_route_backtest
from jesse.services import metrics
import numpy as np


def test_open_pl_and_total_open_trades():
    single_route_backtest('Test40')

    assert len(store.completed_trades.trades) == 1
    assert store.app.total_open_trades == 1
    assert store.app.total_open_pl == 97  # 99 - 2


def test_metrics_for_trades_without_fee():
    single_route_backtest('TestMetrics1')

    trades = store.completed_trades.trades
    assert len(trades) == 1
    stats = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 1
    assert stats['starting_balance'] == 10000
    assert stats['finishing_balance'] == 10050
    assert stats['win_rate'] == 1
    assert stats['ratio_avg_win_loss'] is np.nan
    assert stats['longs_count'] == 1
    assert stats['shorts_count'] == 0
    assert stats['longs_percentage'] == 100
    assert stats['shorts_percentage'] == 0
    assert stats['fee'] == 0
    assert stats['net_profit'] == 50
    assert stats['net_profit_percentage'] == 0.5
    assert stats['average_win'] == 50
    assert stats['average_loss'] is np.nan
    assert stats['expectancy'] == 50
    assert stats['expectancy_percentage'] == 0.5
    assert stats['expected_net_profit_every_100_trades'] == 50
    assert stats['average_holding_period'] == 300
    assert stats['average_losing_holding_period'] is np.nan
    assert stats['average_winning_holding_period'] == 300
    assert stats['gross_loss'] == 0
    assert stats['gross_profit'] == 50
    assert stats['open_pl'] == 0
    assert stats['largest_losing_trade'] == 0
    assert stats['largest_winning_trade'] == 50

    # ignore metrics that are dependant on daily_returns because the testing candle set is not for multiple dais

# def test_stats_for_a_strategy_without_losing_trades():
#     set_up([
#         (exchanges.SANDBOX, 'ETH-USDT', timeframes.MINUTE_5, 'Test08'),
#     ])
#
#     candles = {}
#     key = jh.key(exchanges.SANDBOX, 'ETH-USDT')
#     candles[key] = {
#         'exchange': exchanges.SANDBOX,
#         'symbol': 'ETH-USDT',
#         'candles': test_candles_1
#     }
#
#     # run backtest (dates are fake just to pass)
#     backtest_mode.run('2019-04-01', '2019-04-02', candles)
#     assert len(store.completed_trades.trades) == 1
#     stats_trades = stats.trades(store.completed_trades.trades)
#
#     assert stats_trades == {
#         'total': 1,
#         'starting_balance': 10000,
#         'finishing_balance': 10014.7,
#         'win_rate': 1,
#         'max_R': 1,
#         'min_R': 1,
#         'mean_R': 1,
#         'longs_count': 0,
#         'longs_percentage': 0,
#         'shorts_percentage': 100,
#         'shorts_count': 1,
#         'fee': 0,
#         'pnl': 14.7,
#         'pnl_percentage': 0.15,
#         'average_win': 14.7,
#         'average_loss': np.nan,
#         'expectancy': 14.7,
#         'expectancy_percentage': 0.15,
#         'expected_pnl_every_100_trades': 15.0,
#         'average_holding_period': 180.0,
#         'average_losing_holding_period': np.nan,
#         'average_winning_holding_period': 180.0
#     }


def test_daily_balance_stores_portfolio_value():
    # futures
    single_route_backtest(
        'TestDailyBalanceStoresPortfolioValue',
        is_futures_trading=True,
        candles_count=10*1024
    )

    # spot
    single_route_backtest(
        'TestDailyBalanceStoresPortfolioValue',
        is_futures_trading=False,
        candles_count=10 * 1024
    )
