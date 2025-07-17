from jesse.store import store
from jesse.testing_utils import single_route_backtest
from jesse.services import metrics
import numpy as np
import math


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
    assert stats['sharpe_ratio'] is np.nan
    assert stats['calmar_ratio'] is np.nan
    assert stats['sortino_ratio'] is np.nan
    assert stats['omega_ratio'] is np.nan
    assert stats['serenity_index'] is np.nan
    assert stats['max_drawdown'] == 0


def test_metrics_two_trades_without_fee():
    days = 7
    n_candles = days * 1440
    single_route_backtest('TestMetrics2', trend='sine', candles_count=n_candles, n_waves=1)

    trades = store.completed_trades.trades
    assert len(trades) == 2
    stats = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 2
    assert stats['starting_balance'] == 10000
    assert stats['finishing_balance'] == 10100
    assert stats['longs_percentage'] == 50
    assert stats['shorts_percentage'] == 50
    assert stats['fee'] == 0
    assert 99.9 < stats['net_profit'] <= 100
    assert 0.9 < stats['net_profit_percentage'] <= 1
    assert 49.9 < stats['average_win'] <= 50
    assert stats['average_loss'] is np.nan
    assert stats['win_rate'] == 1.0
    assert stats['winning_streak'] == 2
    assert stats['longs_count'] == 1
    assert stats['shorts_count'] == 1
    assert 49.9 < stats['expectancy'] <= 50
    assert 0.49 < stats['expectancy_percentage'] <= 0.5
    assert stats['gross_loss'] == 0
    assert 99.9 < stats['gross_profit'] <= 100
    assert stats['total_open_trades'] == 1
    assert stats['largest_losing_trade'] == 0
    assert stats['largest_winning_trade'] >= 50
    assert stats['sharpe_ratio'] > 0
    assert stats['calmar_ratio'] > 0
    assert stats['sortino_ratio'] > 0
    assert stats['omega_ratio'] > 0
    assert stats['serenity_index'] > 0
    assert 0 > stats['max_drawdown'] >= -0.5


def test_metrics_long_and_short_without_fee():
    single_route_backtest('TestMetrics2', trend='sine', candles_count=100)

    trades = store.completed_trades.trades
    assert len(trades) == 10
    stats = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 10
    assert stats['starting_balance'] == 10000
    assert stats['finishing_balance'] == 10500
    assert stats['longs_percentage'] == 50
    assert stats['shorts_percentage'] == 50
    assert stats['fee'] == 0
    assert 499.9 < stats['net_profit'] <= 500
    assert 4.9 < stats['net_profit_percentage'] <= 5
    assert 49.9 < stats['average_win'] <= 50
    assert stats['average_loss'] is np.nan
    assert stats['win_rate'] == 1.0
    assert stats['winning_streak'] == 10
    assert stats['longs_count'] == 5
    assert stats['shorts_count'] == 5
    assert 49.9 < stats['expectancy'] <= 50
    assert 0.49 < stats['expectancy_percentage'] <= 0.5
    assert stats['gross_loss'] == 0
    assert 499.9 < stats['gross_profit'] <= 500
    assert stats['total_open_trades'] == 1
    assert stats['largest_losing_trade'] == 0
    assert stats['largest_winning_trade'] >= 50


def test_metrics_long_and_short_one_year_without_fee():
    days = 365
    n_candles = days * 1440  # = 525,600
    single_route_backtest('TestMetrics2', trend='sine', candles_count=n_candles, end_date='2020-04-01')

    trades = store.completed_trades.trades
    assert len(trades) == 10
    stats = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 10
    assert stats['starting_balance'] == 10000
    assert 10499 < stats['finishing_balance'] <= 10500
    assert stats['longs_percentage'] == 50
    assert stats['shorts_percentage'] == 50
    assert stats['fee'] == 0
    assert 499 < stats['net_profit'] <= 500
    assert 4.9 < stats['net_profit_percentage'] <= 5
    assert 49.9 < stats['average_win'] <= 50
    assert stats['average_loss'] is np.nan
    assert stats['win_rate'] == 1.0
    assert stats['winning_streak'] == 10
    assert stats['longs_count'] == 5
    assert stats['shorts_count'] == 5
    assert 49.9 < stats['expectancy'] <= 50
    assert 0.49 < stats['expectancy_percentage'] <= 0.5
    assert stats['gross_loss'] == 0
    assert 499 < stats['gross_profit'] <= 500
    assert stats['total_open_trades'] == 1
    assert stats['largest_losing_trade'] == 0
    assert 49.9 <= stats['largest_winning_trade'] <= 50
    expected_annual_return = ((stats['finishing_balance'] / stats['starting_balance']) ** (365 / days) - 1) * 100
    assert math.isclose(stats['annual_return'], expected_annual_return, abs_tol=1e-1)
    assert stats['max_drawdown'] >= -0.5001 # should never have more than a $50 drawdown
    expected_calmar_ratio = stats['annual_return'] / abs(stats['max_drawdown']) if stats['max_drawdown'] != 0 else float('inf')
    assert math.isclose(stats['calmar_ratio'], expected_calmar_ratio, abs_tol=1e-1)


def test_metrics_fast_long_and_short_one_year_without_fee():
    days = 365
    n_candles = days * 1440  # = 525,600
    single_route_backtest('TestMetrics2', trend='sine', candles_count=n_candles, end_date='2020-04-01', fast_mode=True)

    trades = store.completed_trades.trades
    assert len(trades) == 10
    stats = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 10
    assert stats['starting_balance'] == 10000
    assert 10499 < stats['finishing_balance'] <= 10500
    assert stats['longs_percentage'] == 50
    assert stats['shorts_percentage'] == 50
    assert stats['fee'] == 0
    assert 499 < stats['net_profit'] <= 500
    assert 4.9 < stats['net_profit_percentage'] <= 5
    assert 49.9 < stats['average_win'] <= 50
    assert stats['average_loss'] is np.nan
    assert stats['win_rate'] == 1.0
    assert stats['winning_streak'] == 10
    assert stats['longs_count'] == 5
    assert stats['shorts_count'] == 5
    assert 49.9 < stats['expectancy'] <= 50
    assert 0.49 < stats['expectancy_percentage'] <= 0.5
    assert stats['gross_loss'] == 0
    assert 499 < stats['gross_profit'] <= 500
    assert stats['total_open_trades'] == 1
    assert stats['largest_losing_trade'] == 0
    assert 49.9 <= stats['largest_winning_trade'] <= 50
    expected_annual_return = ((stats['finishing_balance'] / stats['starting_balance']) ** (365 / days) - 1) * 100
    assert math.isclose(stats['annual_return'], expected_annual_return, abs_tol=1e-1)
    assert stats['max_drawdown'] >= -0.5001 # should never have more than a $50 drawdown
    expected_calmar_ratio = stats['annual_return'] / abs(stats['max_drawdown']) if stats['max_drawdown'] != 0 else float('inf')
    assert math.isclose(stats['calmar_ratio'], expected_calmar_ratio, abs_tol=1e-1)


def test_metrics_long_and_short_year_and_half_without_fee():
    days = 548
    n_candles = days * 1440  # = 789,120
    single_route_backtest('TestMetrics2', trend='sine', candles_count=n_candles, end_date='2021-04-01')

    trades = store.completed_trades.trades
    assert len(trades) == 10
    stats = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 10
    assert stats['starting_balance'] == 10000
    assert 10499 < stats['finishing_balance'] <= 10500
    assert stats['longs_percentage'] == 50
    assert stats['shorts_percentage'] == 50
    assert stats['fee'] == 0
    assert 499 < stats['net_profit'] <= 500
    assert 4.9 < stats['net_profit_percentage'] <= 5
    assert 49.9 < stats['average_win'] <= 50
    assert stats['average_loss'] is np.nan
    assert stats['win_rate'] == 1.0
    assert stats['winning_streak'] == 10
    assert stats['longs_count'] == 5
    assert stats['shorts_count'] == 5
    assert 49.9 < stats['expectancy'] <= 50
    assert 0.49 < stats['expectancy_percentage'] <= 0.5
    assert stats['gross_loss'] == 0
    assert 499 < stats['gross_profit'] <= 500
    assert stats['total_open_trades'] == 1
    assert stats['largest_losing_trade'] == 0
    assert 49.9 <= stats['largest_winning_trade'] <= 50
    expected_annual_return = ((stats['finishing_balance'] / stats['starting_balance']) ** (365 / days) - 1) * 100
    assert math.isclose(stats['annual_return'], expected_annual_return, abs_tol=1e-1)
    assert stats['max_drawdown'] >= -0.5001 # should never have more than a $50 drawdown
    expected_calmar_ratio = stats['annual_return'] / abs(stats['max_drawdown']) if stats['max_drawdown'] != 0 else float('inf')
    assert math.isclose(stats['calmar_ratio'], expected_calmar_ratio, abs_tol=1e-1)


def test_metrics_long_and_short_half_year_without_fee():
    days = 183
    n_candles = days * 1440  # = 263520
    single_route_backtest('TestMetrics2', trend='sine', candles_count=n_candles, end_date='2021-04-01')

    trades = store.completed_trades.trades
    assert len(trades) == 10
    stats = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 10
    assert stats['starting_balance'] == 10000
    assert 10499 < stats['finishing_balance'] <= 10500
    assert stats['longs_percentage'] == 50
    assert stats['shorts_percentage'] == 50
    assert stats['fee'] == 0
    assert 499 < stats['net_profit'] <= 500
    assert 4.9 < stats['net_profit_percentage'] <= 5
    assert 49.9 < stats['average_win'] <= 50
    assert stats['average_loss'] is np.nan
    assert stats['win_rate'] == 1.0
    assert stats['winning_streak'] == 10
    assert stats['longs_count'] == 5
    assert stats['shorts_count'] == 5
    assert 49.9 < stats['expectancy'] <= 50
    assert 0.49 < stats['expectancy_percentage'] <= 0.5
    assert stats['gross_loss'] == 0
    assert 499 < stats['gross_profit'] <= 500
    assert stats['total_open_trades'] == 1
    assert stats['largest_losing_trade'] == 0
    assert 49.9 <= stats['largest_winning_trade'] <= 50
    expected_annual_return = ((stats['finishing_balance'] / stats['starting_balance']) ** (365 / days) - 1) * 100
    assert math.isclose(stats['annual_return'], expected_annual_return, abs_tol=1e-1)
    assert stats['max_drawdown'] >= -0.5001 # should never have more than a $50 drawdown
    expected_calmar_ratio = stats['annual_return'] / abs(stats['max_drawdown']) if stats['max_drawdown'] != 0 else float('inf')
    assert math.isclose(stats['calmar_ratio'], expected_calmar_ratio, abs_tol=1e-1)


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
