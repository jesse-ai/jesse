from typing import List, Any, Union

import crypto_empyrical
import numpy as np
import pandas as pd

import jesse.helpers as jh
from jesse.store import store


def candles(candles_array: np.ndarray) -> List[List[str]]:
    period = jh.date_diff_in_days(jh.timestamp_to_arrow(candles_array[0][0]),
                                  jh.timestamp_to_arrow(candles_array[-1][0])) + 1

    if period > 365:
        duration = f'{period} days ({round(period / 365, 2)} years)'
    elif period > 30:
        duration = f'{period} days ({round(period / 30, 2)} months)'
    else:
        duration = f'{period} days'

    return [
        ['period', duration],
        ['starting-ending date', f'{jh.timestamp_to_time(candles_array[0][0])[:10]} => {jh.timestamp_to_time(candles_array[-1][0] + 60_000)[:10]}'],
    ]


def routes(routes: List[Any]) -> List[Union[List[str], List[Any]]]:
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


def trades(trades_list: list, daily_balance: list) -> dict:
    starting_balance = 0
    current_balance = 0

    for e in store.exchanges.storage:
        starting_balance += store.exchanges.storage[e].starting_assets[jh.app_currency()]
        current_balance += store.exchanges.storage[e].assets[jh.app_currency()]

    if len(trades_list) == 0:
        return None

    df = pd.DataFrame.from_records([t.to_dict() for t in trades_list])

    total_completed = len(df)
    winning_trades = df.loc[df['PNL'] > 0]
    total_winning_trades = len(winning_trades)
    losing_trades = df.loc[df['PNL'] < 0]
    total_losing_trades = len(losing_trades)

    arr = df['PNL'].to_numpy()
    pos = np.clip(arr, 0, 1).astype(bool).cumsum()
    neg = np.clip(arr, -1, 0).astype(bool).cumsum()
    current_streak = np.where(arr >= 0, pos - np.maximum.accumulate(np.where(arr <= 0, pos, 0)),
                              -neg + np.maximum.accumulate(np.where(arr >= 0, neg, 0)))

    s_min = current_streak.min()
    losing_streak = 0 if s_min > 0 else abs(s_min)

    s_max = current_streak.max()
    winning_streak = 0 if s_max < 0 else s_max

    largest_losing_trade = df['PNL'].min()
    largest_winning_trade = df['PNL'].max()

    win_rate = len(winning_trades) / (len(losing_trades) + len(winning_trades))
    max_R = df['R'].max()
    min_R = df['R'].min()
    mean_R = df['R'].mean()
    longs_count = len(df.loc[df['type'] == 'long'])
    shorts_count = len(df.loc[df['type'] == 'short'])
    longs_percentage = longs_count / (longs_count + shorts_count) * 100
    short_percentage = 100 - longs_percentage
    fee = df['fee'].sum()
    net_profit = df['PNL'].sum()
    net_profit_percentage = (net_profit / starting_balance) * 100
    average_win = winning_trades['PNL'].mean()
    average_loss = abs(losing_trades['PNL'].mean())
    ratio_avg_win_loss = average_win / average_loss
    expectancy = (0 if np.isnan(average_win) else average_win) * win_rate - (
        0 if np.isnan(average_loss) else average_loss) * (1 - win_rate)
    expectancy = expectancy
    expectancy_percentage = (expectancy / starting_balance) * 100
    expected_net_profit_every_100_trades = expectancy_percentage * 100
    average_holding_period = df['holding_period'].mean()
    average_winning_holding_period = winning_trades['holding_period'].mean()
    average_losing_holding_period = losing_trades['holding_period'].mean()
    gross_profit = df.loc[df['PNL'] > 0]['PNL'].sum()
    gross_loss = df.loc[df['PNL'] < 0]['PNL'].sum()

    daily_returns = pd.Series(daily_balance).pct_change(1).values
    max_drawdown = crypto_empyrical.max_drawdown(daily_returns) * 100
    annual_return = crypto_empyrical.annual_return(daily_returns) * 100
    sharpe_ratio = crypto_empyrical.sharpe_ratio(daily_returns)
    calmar_ratio = crypto_empyrical.calmar_ratio(daily_returns)
    sortino_ratio = crypto_empyrical.sortino_ratio(daily_returns)
    omega_ratio = crypto_empyrical.omega_ratio(daily_returns)
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
        'current_streak': current_streak[-1],
    }
