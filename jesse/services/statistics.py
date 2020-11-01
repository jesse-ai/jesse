import empyrical
import numpy as np
import pandas as pd

import jesse.helpers as jh
from jesse.store import store


def candles(candles_array):
    period = jh.date_diff_in_days(jh.get_arrow(candles_array[0][0]), jh.get_arrow(candles_array[-1][0])) + 1

    if period > 365:
        duration = '{} days ({} years)'.format(period, round(period / 365, 2))
    elif period > 30:
        duration = '{} days ({} months)'.format(period, round(period / 30, 2))
    else:
        duration = '{} days'.format(period)

    return [
        ['period', duration],
        ['starting-ending date', '{} => {}'.format(jh.timestamp_to_time(candles_array[0][0])[:10],
                                                   jh.timestamp_to_time(candles_array[-1][0] + 60_000)[:10])],
    ]


def routes(routes):
    array = []

    # header
    array.append(['exchange', 'symbol', 'timeframe', 'strategy', 'DNA'])

    for r in routes:
        array.append([
            r.exchange,
            r.symbol,
            r.timeframe,
            r.strategy_name,
            r.dna
        ])

    return array


def trades(trades_list: list, daily_balance: list):
    starting_balance = 0
    current_balance = 0

    for e in store.exchanges.storage:
        starting_balance += store.exchanges.storage[e].starting_assets[jh.app_currency()]
        current_balance += store.exchanges.storage[e].assets[jh.app_currency()]

    starting_balance = round(starting_balance, 2)
    current_balance = round(current_balance, 2)

    if len(trades_list) == 0:
        return None

    df = pd.DataFrame.from_records([t.to_dict() for t in trades_list])

    total_completed = len(df)
    winning_trades = df.loc[df['PNL'] > 0]
    total_winning_trades = len(winning_trades)
    losing_trades = df.loc[df['PNL'] < 0]
    total_losing_trades = len(losing_trades)

    losing_i = df['PNL'] < 0
    losing_streaks = losing_i.ne(losing_i.shift()).cumsum()
    losing_streak = losing_streaks[losing_i].value_counts().max()

    winning_i = df['PNL'] > 0
    winning_streaks = winning_i.ne(winning_i.shift()).cumsum()
    winning_streak = winning_streaks[winning_i].value_counts().max()
    largest_losing_trade = round(df['PNL'].min(), 2)
    largest_winning_trade = round(df['PNL'].max(), 2)

    win_rate = len(winning_trades) / (len(losing_trades) + len(winning_trades))
    max_R = round(df['R'].max(), 2)
    min_R = round(df['R'].min(), 2)
    mean_R = round(df['R'].mean(), 2)
    longs_count = len(df.loc[df['type'] == 'long'])
    shorts_count = len(df.loc[df['type'] == 'short'])
    longs_percentage = longs_count / (longs_count + shorts_count) * 100
    short_percentage = 100 - longs_percentage
    fee = df['fee'].sum()
    net_profit = round(df['PNL'].sum(), 2)
    net_profit_percentage = round((net_profit / starting_balance) * 100, 2)
    average_win = round(winning_trades['PNL'].mean(), 2)
    average_loss = round(abs(losing_trades['PNL'].mean()), 2)
    ratio_avg_win_loss = average_win / average_loss
    expectancy = (0 if np.isnan(average_win) else average_win) * win_rate - (
        0 if np.isnan(average_loss) else average_loss) * (1 - win_rate)
    expectancy = round(expectancy, 2)
    expectancy_percentage = round((expectancy / starting_balance) * 100, 2)
    expected_net_profit_every_100_trades = round(expectancy_percentage * 100, 2)
    average_holding_period = df['holding_period'].mean()
    average_winning_holding_period = winning_trades['holding_period'].mean()
    average_losing_holding_period = losing_trades['holding_period'].mean()
    gross_profit = round(df.loc[df['PNL'] > 0]['PNL'].sum(), 2)
    gross_loss = round(df.loc[df['PNL'] < 0]['PNL'].sum(), 2)

    daily_returns = pd.Series(daily_balance).pct_change(1).values
    max_drawdown = round(empyrical.max_drawdown(daily_returns) * 100, 2)
    annual_return = round(empyrical.annual_return(daily_returns) * 100, 2)
    sharpe_ratio = round(empyrical.sharpe_ratio(daily_returns), 2)
    calmar_ratio = round(empyrical.calmar_ratio(daily_returns), 2)
    sortino_ratio = round(empyrical.sortino_ratio(daily_returns), 2)
    omega_ratio = round(empyrical.omega_ratio(daily_returns), 2)
    total_open_trades = store.app.total_open_trades
    open_pl = store.app.total_open_pl

    return {
        'total': np.nan if np.isnan(total_completed) else total_completed,
        'total_winning_trades': np.nan if np.isnan(total_winning_trades) else total_winning_trades,
        'total_losing_trades': np.nan if np.isnan(total_losing_trades) else total_losing_trades,
        'starting_balance': np.nan if np.isnan(starting_balance) else starting_balance,
        'finishing_balance': np.nan if np.isnan(current_balance) else current_balance,
        'win_rate': np.nan if np.isnan(win_rate) else win_rate,
        'max_R': np.nan if np.isnan(max_R) else max_R,
        'min_R': np.nan if np.isnan(min_R) else min_R,
        'mean_R': np.nan if np.isnan(mean_R) else mean_R,
        'ratio_avg_win_loss': np.nan if np.isnan(ratio_avg_win_loss) else ratio_avg_win_loss,
        'longs_count': np.nan if np.isnan(longs_count) else longs_count,
        'longs_percentage': np.nan if np.isnan(longs_percentage) else longs_percentage,
        'short_percentage': np.nan if np.isnan(short_percentage) else short_percentage,
        'shorts_count': np.nan if np.isnan(shorts_count) else shorts_count,
        'fee': np.nan if np.isnan(fee) else fee,
        'net_profit': np.nan if np.isnan(net_profit) else net_profit,
        'net_profit_percentage': np.nan if np.isnan(net_profit_percentage) else net_profit_percentage,
        'average_win': np.nan if np.isnan(average_win) else average_win,
        'average_loss': np.nan if np.isnan(average_loss) else average_loss,
        'expectancy': np.nan if np.isnan(expectancy) else expectancy,
        'expectancy_percentage': np.nan if np.isnan(expectancy_percentage) else expectancy_percentage,
        'expected_net_profit_every_100_trades': np.nan if np.isnan(
            expected_net_profit_every_100_trades) else expected_net_profit_every_100_trades,
        'average_holding_period': average_holding_period,
        'average_winning_holding_period': average_winning_holding_period,
        'average_losing_holding_period': average_losing_holding_period,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'max_drawdown': max_drawdown,
        'annual_return': annual_return,
        'sharpe_ratio': sharpe_ratio,
        'calmar_ratio': calmar_ratio,
        'sortino_ratio': sortino_ratio,
        'omega_ratio': omega_ratio,
        'total_open_trades': total_open_trades,
        'open_pl': open_pl,
        'winning_streak': winning_streak,
        'losing_streak': losing_streak,
        'largest_losing_trade': largest_losing_trade,
        'largest_winning_trade': largest_winning_trade,
    }
