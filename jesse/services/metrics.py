from datetime import datetime
from typing import List

import numpy as np
import pandas as pd

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


def _prepare_returns(returns, rf=0.0, periods=252):
    """
    Helper function to prepare returns data by converting to pandas Series and 
    adjusting for risk-free rate if provided
    """
    if isinstance(returns, pd.DataFrame):
        returns = returns[returns.columns[0]]

    if rf != 0:
        returns = returns - (rf / periods)

    return returns


def sharpe_ratio(prepared_returns, rf=0.0, periods=365, annualize=True, smart=False):
    """
    Calculates the sharpe ratio of access returns
    """
    if prepared_returns.empty or len(prepared_returns) == 1:
        return np.nan
    
    if isinstance(prepared_returns, pd.DataFrame):
         prepared_returns = _prepare_returns(prepared_returns, rf, periods)

    divisor = prepared_returns.std(ddof=1)
    
    if smart:
        divisor = divisor * autocorr_penalty(prepared_returns)
        
    res = prepared_returns.mean() / divisor
    
    if annualize:
        res = res * np.sqrt(1 if periods is None else periods)
    
    return res


def sortino_ratio(prepared_returns, rf=0.0, periods=365, annualize=True, smart=False):
    """
    Calculates the Sortino ratio of excess returns.
    """
    if prepared_returns.empty or len(prepared_returns) == 1:
        return np.nan

    if isinstance(prepared_returns, pd.DataFrame):
         prepared_returns = _prepare_returns(prepared_returns, rf, periods)

    # downside deviation based on negative returns only
    negative_returns = prepared_returns[prepared_returns < 0]

    if len(negative_returns) < 2:
        return np.nan  # not enough downside data

    downside = negative_returns.std(ddof=1)

    if downside == 0 or np.isnan(downside):
        res = np.inf if prepared_returns.mean() > 0 else -np.inf
    else:
        if smart:
            downside = downside * autocorr_penalty(prepared_returns)

        res = prepared_returns.mean() / downside

        if annualize:
            res *= np.sqrt(1 if periods is None else periods)

    return res


def autocorr_penalty(returns):
    """
    Calculates the autocorrelation penalty for returns
    """
    num = len(returns)
    coef = np.abs(np.corrcoef(returns[:-1], returns[1:])[0, 1])
    corr = [((num - x) / num) * coef**x for x in range(1, num)]
    return np.sqrt(1 + 2 * np.sum(corr))


def calmar_ratio(prepared_returns):
    """
    Calculates the calmar ratio (CAGR% / MaxDD%)
    """
    if prepared_returns.empty:
        return np.nan  # empty input → undefined

    if isinstance(prepared_returns, pd.DataFrame):
         prepared_returns = _prepare_returns(prepared_returns)

    if len(prepared_returns) <= 1:
        return np.nan  # not enough data to compute CAGR meaningfully

    # Calculate CAGR
    calculated_cagr = cagr(prepared_returns)
    if calculated_cagr is np.nan:
        return np.nan
    max_dd = abs(max_drawdown(prepared_returns))

    return calculated_cagr / max_dd if max_dd != 0 else 0


def max_drawdown(returns):
    """
    Calculates the maximum drawdown
    """
    if returns.empty:
        return np.nan

    prices = (returns + 1).cumprod()
    return (prices / prices.expanding(min_periods=0).max()).min() - 1


def cagr(prepared_returns, rf=0.0):
    """
    Calculates the communicative annualized growth return (CAGR%)
    """
    if prepared_returns.empty:
        return np.nan
    
    if isinstance(prepared_returns, pd.DataFrame):
         prepared_returns = _prepare_returns(prepared_returns, rf)
    
    # Get first and last values of cumulative returns
    first_value = 1
    last_value = (1 + prepared_returns).prod()
    
    # Calculate years exactly as quantstats does
    days = len(prepared_returns) + 1 # Need to add one because of pct_change() taking one off
        
    # Calculate CAGR using quantstats formula
    result = (last_value / first_value) ** (365 / days) - 1
    
    return result


def omega_ratio(prepared_returns, rf=0.0, required_return=0.0, periods=365):
    """
    Determines the Omega ratio of a strategy
    """
    if prepared_returns.empty:
        return np.nan

    if isinstance(prepared_returns, pd.DataFrame):
         prepared_returns = _prepare_returns(prepared_returns, rf, periods)
    
    if periods == 1:
        return_threshold = required_return
    else:
        return_threshold = (1 + required_return) ** (1.0 / periods) - 1
        
    returns_less_thresh = prepared_returns - return_threshold
    numer = returns_less_thresh[returns_less_thresh > 0.0].sum()
    denom = -1.0 * returns_less_thresh[returns_less_thresh < 0.0].sum()
    
    result = numer / denom if denom > 0.0 else np.nan
    
    return result


def serenity_index(returns, rf=0):
    """
    Calculates the serenity index score
    """
    if returns.empty or len(returns) == 1:
        return np.nan

    dd = to_drawdown_series(returns)
    pitfall = -conditional_value_at_risk(dd) / returns.std()
    result = (returns.sum() - rf) / (ulcer_index(returns) * pitfall)
    
    return result


def ulcer_index(returns):
    """
    Calculates the ulcer index score (downside risk measurement)
    """
    dd = to_drawdown_series(returns)
    return np.sqrt(np.divide((dd**2).sum(), returns.shape[0] - 1))


def to_drawdown_series(returns):
    """
    Convert returns series to drawdown series
    """
    prices = (1 + returns).cumprod()
    dd = prices / np.maximum.accumulate(prices) - 1.0
    return dd.replace([np.inf, -np.inf, -0], 0)


def conditional_value_at_risk(returns, sigma=1, confidence=0.95):
    """
    Calculates the conditional daily value-at-risk (aka expected shortfall)
    """
    if len(returns) < 2:
        return 0
        
    returns = _prepare_returns(returns)
    # Sort returns from worst to best
    sorted_returns = np.sort(returns)
    # Find the index based on confidence level
    index = int((1 - confidence) * len(sorted_returns))
    
    # Handle empty slice warning
    if index == 0:
        return sorted_returns[0] if len(sorted_returns) > 0 else 0
        
    # Calculate CVaR as the mean of worst losses
    c_var = sorted_returns[:index].mean()
    return c_var if ~np.isnan(c_var) else 0


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

    daily_return = pd.DataFrame(daily_balance, index=date_index).pct_change(1).dropna()

    total_open_trades = store.app.total_open_trades
    open_pl = store.app.total_open_pl

    # Helper function to safely convert values
    def safe_convert(value, convert_type=float):
        try:
            if isinstance(value, pd.Series):
                value = value.iloc[0]
            if np.isnan(value):
                return np.nan
            return convert_type(value)
        except:
            return np.nan

    # Calculate metrics using 365 days for crypto markets
    prepared_returns = _prepare_returns(daily_return, periods=365)
    max_dd = max_drawdown(daily_return) * 100
    annual_return = cagr(prepared_returns) * 100
    sharpe = sharpe_ratio(prepared_returns, periods=365)
    calmar = calmar_ratio(prepared_returns)
    sortino = sortino_ratio(prepared_returns, periods=365)
    omega = omega_ratio(prepared_returns, periods=365)
    serenity = serenity_index(daily_return)

    return {
        'total': safe_convert(total_completed, int),
        'total_winning_trades': safe_convert(total_winning_trades, int),
        'total_losing_trades': safe_convert(total_losing_trades, int),
        'starting_balance': safe_convert(starting_balance),
        'finishing_balance': safe_convert(current_balance),
        'win_rate': safe_convert(win_rate),
        'ratio_avg_win_loss': safe_convert(ratio_avg_win_loss),
        'longs_count': safe_convert(longs_count, int),
        'longs_percentage': safe_convert(longs_percentage),
        'shorts_percentage': safe_convert(shorts_percentage),
        'shorts_count': safe_convert(shorts_count, int),
        'fee': safe_convert(fee),
        'net_profit': safe_convert(net_profit),
        'net_profit_percentage': safe_convert(net_profit_percentage),
        'average_win': safe_convert(average_win),
        'average_loss': safe_convert(average_loss),
        'expectancy': safe_convert(expectancy),
        'expectancy_percentage': safe_convert(expectancy_percentage),
        'expected_net_profit_every_100_trades': safe_convert(expected_net_profit_every_100_trades),
        'average_holding_period': safe_convert(average_holding_period),
        'average_winning_holding_period': safe_convert(average_winning_holding_period),
        'average_losing_holding_period': safe_convert(average_losing_holding_period),
        'gross_profit': safe_convert(gross_profit),
        'gross_loss': safe_convert(gross_loss),
        'max_drawdown': safe_convert(max_dd),
        'annual_return': safe_convert(annual_return),
        'sharpe_ratio': safe_convert(sharpe),
        'calmar_ratio': safe_convert(calmar),
        'sortino_ratio': safe_convert(sortino),
        'omega_ratio': safe_convert(omega),
        'serenity_index': safe_convert(serenity),
        'total_open_trades': safe_convert(total_open_trades, int),
        'open_pl': safe_convert(open_pl),
        'winning_streak': safe_convert(winning_streak, int),
        'losing_streak': safe_convert(losing_streak, int),
        'largest_losing_trade': safe_convert(largest_losing_trade),
        'largest_winning_trade': safe_convert(largest_winning_trade),
        'current_streak': safe_convert(current_streak[-1], int),
    }


def hyperparameters(routes_arr: list) -> list:
    if routes_arr[0].strategy.hp is None:
        return []
    # only for the first route
    hp = []

    # add DNA
    dna_value = routes_arr[0].strategy.dna()
    if dna_value is not None and len(dna_value) > 16:
        formatted_dna = f"{dna_value[:5]}*****{dna_value[-5:]}"
        hp.append(['DNA', formatted_dna])
    else:
        hp.append(['DNA', dna_value])

    # add hyperparameters
    for key in routes_arr[0].strategy.hp:
        hp.append([
            key, routes_arr[0].strategy.hp[key]
        ])
    return hp
