from datetime import datetime, timedelta
from typing import Any, List, Union

import numpy as np
import pandas as pd
from quantstats import stats

import jesse.helpers as jh
from jesse.models import ClosedTrade
from jesse.services import selectors
from jesse.store import store


def candles_info(candles_array: np.ndarray) -> dict:
    period = jh.date_diff_in_days(
        jh.timestamp_to_arrow(candles_array[0][0]),
        jh.timestamp_to_arrow(candles_array[-1][0])) + 1

    if period > 365:
        duration = f'{period} days ({round(period / 365, 2)} years)'
    elif period > 30:
        duration = f'{period} days ({round(period / 30, 2)} months)'
    else:
        duration = f'{period} days'

    # type of the exchange
    trading_exchange = selectors.get_trading_exchange()

    info = {
        'duration': duration,
        'starting_time': candles_array[0][0],
        'finishing_time': (candles_array[-1][0] + 60_000),
        'exchange_type': trading_exchange.type,
        'exchange': trading_exchange.name,
    }

    # if the exchange type is futures, also display leverage
    if trading_exchange.type == 'futures':
        info['leverage'] = trading_exchange.futures_leverage
        info['leverage_mode'] = trading_exchange.futures_leverage_mode

    return info


def routes(routes_arr: list) -> list:
    return [{
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'strategy_name': r.strategy_name,
        } for r in routes_arr]


def trades(trades_list: List[ClosedTrade], daily_balance: list, final: bool = True) -> dict:
    starting_balance = 0
    current_balance = 0

    for e in store.exchanges.storage:
        starting_balance += store.exchanges.storage[e].starting_assets[jh.app_currency()]
        current_balance += store.exchanges.storage[e].assets[jh.app_currency()]

    if not trades_list:
        return {'total': 0, 'win_rate': 0, 'net_profit_percentage': 0}

    df = pd.DataFrame.from_records([t.to_dict for t in trades_list])

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
    winning_streak = max(s_max, 0)

    largest_losing_trade = 0 if total_losing_trades == 0 else losing_trades['PNL'].min()
    largest_winning_trade = 0 if total_winning_trades == 0 else winning_trades['PNL'].max()
    if len(winning_trades) == 0:
        win_rate = 0
    else:
        win_rate = len(winning_trades) / (len(losing_trades) + len(winning_trades))
    longs_count = len(df.loc[df['type'] == 'long'])
    shorts_count = len(df.loc[df['type'] == 'short'])
    longs_percentage = longs_count / (longs_count + shorts_count) * 100
    shorts_percentage = 100 - longs_percentage
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
    gross_profit = winning_trades['PNL'].sum()
    gross_loss = losing_trades['PNL'].sum()

    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    date_index = pd.date_range(start=start_date, periods=len(daily_balance))

    daily_return = pd.DataFrame(daily_balance, index=date_index).pct_change(1)

    total_open_trades = store.app.total_open_trades
    open_pl = store.app.total_open_pl


    max_drawdown = np.nan
    annual_return = np.nan
    sharpe_ratio = np.nan
    calmar_ratio = np.nan
    sortino_ratio = np.nan
    omega_ratio = np.nan
    serenity_index = np.nan
    smart_sharpe = np.nan
    smart_sortino = np.nan

    if len(daily_return) > 2:
        max_drawdown = stats.max_drawdown(daily_return).values[0] * 100
        annual_return = stats.cagr(daily_return).values[0] * 100
        sharpe_ratio = stats.sharpe(daily_return, periods=365).values[0]
        calmar_ratio = stats.calmar(daily_return).values[0]
        sortino_ratio = stats.sortino(daily_return, periods=365).values[0]
        omega_ratio = stats.omega(daily_return, periods=365)
        serenity_index = stats.serenity_index(daily_return).values[0]
        # As those calculations are slow they are only done for the final report and not at self.metrics in the strategy.
        if final:
            smart_sharpe = stats.smart_sharpe(daily_return, periods=365).values[0]
            smart_sortino = stats.smart_sortino(daily_return, periods=365).values[0]

    return {
        'total': np.nan if np.isnan(total_completed) else total_completed,
        'total_winning_trades': np.nan if np.isnan(total_winning_trades) else total_winning_trades,
        'total_losing_trades': np.nan if np.isnan(total_losing_trades) else total_losing_trades,
        'starting_balance': np.nan if np.isnan(starting_balance) else starting_balance,
        'finishing_balance': np.nan if np.isnan(current_balance) else current_balance,
        'win_rate': np.nan if np.isnan(win_rate) else win_rate,
        'ratio_avg_win_loss': np.nan if np.isnan(ratio_avg_win_loss) else ratio_avg_win_loss,
        'longs_count': np.nan if np.isnan(longs_count) else longs_count,
        'longs_percentage': np.nan if np.isnan(longs_percentage) else longs_percentage,
        'shorts_percentage': np.nan if np.isnan(shorts_percentage) else shorts_percentage,
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
        'max_drawdown': np.nan if np.isnan(max_drawdown) else max_drawdown,
        'annual_return': np.nan if np.isnan(annual_return) else annual_return,
        'sharpe_ratio': np.nan if np.isnan(sharpe_ratio) else sharpe_ratio,
        'calmar_ratio': np.nan if np.isnan(calmar_ratio) else calmar_ratio,
        'sortino_ratio': np.nan if np.isnan(sortino_ratio) else sortino_ratio,
        'omega_ratio': np.nan if np.isnan(omega_ratio) else omega_ratio,
        'serenity_index': np.nan if np.isnan(serenity_index) else serenity_index,
        'smart_sharpe': np.nan if np.isnan(smart_sharpe) else smart_sharpe,
        'smart_sortino': np.nan if np.isnan(smart_sortino) else smart_sortino,
        'total_open_trades': total_open_trades,
        'open_pl': open_pl,
        'winning_streak': winning_streak,
        'losing_streak': losing_streak,
        'largest_losing_trade': largest_losing_trade,
        'largest_winning_trade': largest_winning_trade,
        'current_streak': current_streak[-1],
    }


def hyperparameters(routes_arr: list) -> list:
    if routes_arr[0].strategy.hp is None:
        return []
    # only for the first route
    hp = []

    # add DNA
    hp.append(['DNA', routes_arr[0].strategy.dna()])

    # add hyperparameters
    for key in routes_arr[0].strategy.hp:
        hp.append([
            key, routes_arr[0].strategy.hp[key]
        ])
    return hp
