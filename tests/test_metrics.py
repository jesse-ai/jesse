import jesse.helpers as jh
from jesse.config import config, reset_config
from jesse.enums import exchanges
from jesse.factories import fake_range_candle_from_range_prices
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.store import store


def get_btc_and_eth_candles():
    candles = {}
    candles[jh.key(exchanges.SANDBOX, 'BTCUSDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTCUSDT',
        'candles': fake_range_candle_from_range_prices(range(101, 200))
    }
    candles[jh.key(exchanges.SANDBOX, 'ETHUSDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'ETHUSDT',
        'candles': fake_range_candle_from_range_prices(range(1, 100))
    }
    return candles


def get_btc_candles():
    candles = {}
    candles[jh.key(exchanges.SANDBOX, 'BTCUSDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTCUSDT',
        'candles': fake_range_candle_from_range_prices(range(1, 100))
    }
    return candles


def set_up(routes, fee=0):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['assets'] = [
        {'asset': 'USDT', 'balance': 1000},
        {'asset': 'BTC', 'balance': 0},
    ]
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'margin'
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = fee
    router.set_routes(routes)
    router.set_extra_candles([])
    store.reset(True)


def test_open_pl_and_total_open_trades():
    set_up([(exchanges.SANDBOX, 'BTCUSDT', '1m', 'Test40')])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 0
    assert store.app.total_open_trades == 1
    assert store.app.total_open_pl == 97  # 99 - 2

# def test_statistics_for_trades_without_fee():
#     set_up([
#         (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test06'),
#     ])
#
#     candles = {}
#     key = jh.key(exchanges.SANDBOX, 'ETHUSDT')
#     candles[key] = {
#         'exchange': exchanges.SANDBOX,
#         'symbol': 'ETHUSDT',
#         'candles': test_candles_1
#     }
#
#     # run backtest (dates are fake just to pass)
#     backtest_mode.run('2019-04-01', '2019-04-02', candles)
#     assert len(store.completed_trades.trades) == 2
#     stats_trades = stats.trades(store.completed_trades.trades, store.app.daily_balance)
#
#     assert stats_trades == {
#         'total': 2,
#         'starting_balance': 10000,
#         'finishing_balance': 10004.7,
#         'win_rate': 0.5,
#         'ratio_avg_win_loss': 1.47,
#         'longs_count': 1,
#         'longs_percentage': 50.0,
#         'short_percentage': 50.0,
#         'shorts_count': 1,
#         'fee': 0,
#         'net_profit': 4.7,
#         'net_profit_percentage': 0.05,
#         'sharpe_ratio': np.nan,
#         'average_win': 14.7,
#         'average_loss': 10,
#         'expectancy': 2.35,
#         'expectancy_percentage': 0.02,
#         'expected_net_profit_every_100_trades': 2,
#         'average_holding_period': 960.0,
#         'average_losing_holding_period': 1740.0,
#         'average_winning_holding_period': 180.0,
#         'gross_loss': -10,
#         'gross_profit': 14.7,
#         'max_drawdown': 0,
#         'annual_return': 6.1
#     }
#
#
# def test_stats_for_a_strategy_without_losing_trades():
#     set_up([
#         (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test08'),
#     ])
#
#     candles = {}
#     key = jh.key(exchanges.SANDBOX, 'ETHUSDT')
#     candles[key] = {
#         'exchange': exchanges.SANDBOX,
#         'symbol': 'ETHUSDT',
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
#         'short_percentage': 100,
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
#
#
# def test_stats_for_a_strategy_without_any_trades():
#     set_up([
#         (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test09'),
#     ])
#
#     candles = {}
#     key = jh.key(exchanges.SANDBOX, 'ETHUSDT')
#     candles[key] = {
#         'exchange': exchanges.SANDBOX,
#         'symbol': 'ETHUSDT',
#         'candles': test_candles_1
#     }
#
#     # run backtest (dates are fake just to pass)
#     backtest_mode.run('2019-04-01', '2019-04-02', candles)
#     assert len(store.completed_trades.trades) == 0
#     stats_trades = stats.trades(store.completed_trades.trades)
#
#     assert stats_trades == {
#         'total': 0,
#         'starting_balance': 10000,
#         'finishing_balance': 10000,
#         'win_rate': np.nan,
#         'max_R': np.nan,
#         'min_R': np.nan,
#         'mean_R': np.nan,
#         'longs_count': np.nan,
#         'longs_percentage': np.nan,
#         'short_percentage': np.nan,
#         'shorts_count': np.nan,
#         'fee': np.nan,
#         'pnl': np.nan,
#         'pnl_percentage': np.nan,
#         'average_win': np.nan,
#         'average_loss': np.nan,
#         'expectancy': np.nan,
#         'expectancy_percentage': np.nan,
#         'expected_pnl_every_100_trades': np.nan,
#         'average_holding_period': np.nan,
#         'average_winning_holding_period': np.nan,
#         'average_losing_holding_period': np.nan,
#     }
#
# #
# #
# # def test_statistics_for_trades_with_fee():
# #     set_up([
# #         (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test06'),
# #     ], 0.002)
# #
# #     candles = {}
# #     key = jh.key(exchanges.SANDBOX, 'ETHUSDT')
# #     candles[key] = {
# #         'exchange': exchanges.SANDBOX,
# #         'symbol': 'ETHUSDT',
# #         'candles': test_candles_1
# #     }
# #
# #     # run backtest (dates are fake just to pass)
# #     backtest_mode('2019-04-01', '2019-04-02', candles)
# #     assert len(store.completed_trades.trades) == 2
# #     stats_trades = stats.trades(store.completed_trades.trades)
# #
# #     assert stats_trades == [
# #         ['total', 2],
# #         ['starting balance', 10000],
# #         ['finishing balance', 9994.29],
# #         ['fee', 10.35],
# #         ['PNL', -5.6514],
# #         ['PNL%', '-0.06%'],
# #         ['PNL% every 100 trades', '-2.83%'],
# #         ['expectancy', -2.83],
# #         ['expectancy%', '-0.03%'],
# #         ['average win', 9.61],
# #         ['average loss', 15.26],
# #         ['win rate', '50%'],
# #         ['min R', 1],
# #         ['average R', 1.5],
# #         ['max R', 2],
# #         ['longs/shorts trades', '50%/50%'],
# #     ]
