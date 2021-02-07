# silent (pandas) warnings
import warnings
from typing import List, Any, Union, Dict, Optional

import numpy as np
import pandas as pd
from peewee import CharField, FloatField

import jesse.helpers as jh
from jesse.config import config
from jesse.routes import router
from jesse.services import metrics as stats
from jesse.services import selectors
from jesse.services.candle import is_bullish
from jesse.store import store

warnings.filterwarnings("ignore")


def positions() -> List[Union[List[str], List[Union[Union[str, int, None], Any]]]]:
    array = []

    # headers
    array.append(['type', 'strategy', 'symbol', 'opened at', 'qty', 'entry', 'current price', 'PNL (%)'])

    for p in store.positions.storage:
        pos = store.positions.storage[p]

        if pos.pnl_percentage > 0:
            pnl_color = 'green'
        elif pos.pnl_percentage < 0:
            pnl_color = 'red'
        else:
            pnl_color = 'black'

        if pos.type == 'long':
            type_color = 'green'
        elif pos.type == 'short':
            type_color = 'red'
        else:
            type_color = 'black'

        array.append(
            [
                jh.color(pos.type, type_color),
                pos.strategy.name,
                pos.symbol,
                '' if pos.is_close else '{} ago'.format(
                    jh.readable_duration((jh.now_to_timestamp() - pos.opened_at) / 1000, 3)),
                pos.qty if abs(pos.qty) > 0 else None,
                pos.entry_price,
                pos.current_price,
                '' if pos.is_close else '{} ({}%)'.format(
                    jh.color(str(round(pos.pnl, 2)), pnl_color),
                    jh.color(str(round(pos.pnl_percentage, 4)), pnl_color)
                ),
            ]
        )
    return array


def candles() -> List[List[str]]:
    array = []
    candle_keys = []

    # add routes
    for e in router.routes:
        if e.strategy is None:
            return

        candle_keys.append({
            'exchange': e.exchange,
            'symbol': e.symbol,
            'timeframe': e.timeframe
        })

    # add extra_routes
    for e in router.extra_candles:
        candle_keys.append({
            'exchange': e[0],
            'symbol': e[1],
            'timeframe': e[2]
        })

    # headers
    array.append(['exchange-symbol-timeframe', 'timestamp', 'open', 'close', 'high', 'low'])

    for k in candle_keys:
        try:
            current_candle = store.candles.get_current_candle(k['exchange'], k['symbol'], k['timeframe'])
            green = is_bullish(current_candle)
            bold = k['symbol'] in config['app']['trading_symbols'] and k['timeframe'] in config['app'][
                'trading_timeframes']
            key = jh.key(k['exchange'], k['symbol'], k['timeframe'])
            array.append(
                [
                    jh.style(key, 'underline' if bold else None),
                    jh.color(jh.timestamp_to_time(current_candle[0]), 'green' if green else 'red'),
                    jh.color(str(current_candle[1]), 'green' if green else 'red'),
                    jh.color(str(current_candle[2]), 'green' if green else 'red'),
                    jh.color(str(current_candle[3]), 'green' if green else 'red'),
                    jh.color(str(current_candle[4]), 'green' if green else 'red'),
                ]
            )
        except IndexError:
            return
        except Exception:
            raise
    return array


def livetrade() -> List[Union[List[Union[str, Any]], List[str], List[Union[str, int]], List[Union[
    str, Dict[str, Union[str, int]], Dict[str, str], Dict[str, bool], Dict[str, Union[
        Dict[str, Union[int, str, List[Dict[str, Union[str, int]]]]], Dict[
            str, Union[float, str, int, List[Dict[str, Union[str, int]]]]]]], Dict[str, int]]]]]:
    # sum up balance of all trading exchanges
    starting_balance = 0
    current_balance = 0
    for e in store.exchanges.storage:
        starting_balance += store.exchanges.storage[e].starting_assets[jh.app_currency()]
        current_balance += store.exchanges.storage[e].assets[jh.app_currency()]
    starting_balance = round(starting_balance, 2)
    current_balance = round(current_balance, 2)

    arr = [
        ['started at', jh.timestamp_to_arrow(store.app.starting_time).humanize()],
        ['current time', jh.timestamp_to_time(jh.now_to_timestamp())[:19]],
        ['errors/info', '{}/{}'.format(len(store.logs.errors), len(store.logs.info))],
        ['active orders', store.orders.count_all_active_orders()],
        ['open positions', store.positions.count_open_positions()]
    ]

    # TODO: for now, we assume that we trade on one exchange only. Later, we need to support for more than one exchange at a time
    first_exchange = selectors.get_exchange(router.routes[0].exchange)

    if first_exchange.type == 'futures':
        arr.append(['started/current balance', '{}/{}'.format(starting_balance, current_balance)])
    else:
        # loop all trading exchanges
        for exchange in selectors.get_all_exchanges():
            # loop all assets
            for asset_name, asset_balance in exchange.assets.items():
                if asset_name == jh.base_asset(router.routes[0].symbol):
                    current_price = selectors.get_current_price(router.routes[0].exchange, router.routes[0].symbol)
                    arr.append(
                        [
                            '{}'.format(asset_name),
                            '{}/{} ({} {})'.format(
                                round(exchange.available_assets[asset_name], 5),
                                round(asset_balance, 5),
                                jh.format_currency(round(asset_balance * current_price, 2)),
                                jh.quote_asset(router.routes[0].symbol)
                            )
                        ]
                    )
                else:
                    arr.append(
                        [
                            '{}'.format(asset_name),
                            '{}/{}'.format(
                                round(exchange.available_assets[asset_name], 5),
                                round(asset_balance, 5),
                            )
                        ]
                    )

    # short trades summary
    if len(store.completed_trades.trades):
        df = pd.DataFrame.from_records([t.to_dict() for t in store.completed_trades.trades])
        total = len(df)
        winning_trades = df.loc[df['PNL'] > 0]
        losing_trades = df.loc[df['PNL'] < 0]
        pnl = round(df['PNL'].sum(), 2)
        pnl_percentage = round((pnl / starting_balance) * 100, 2)

        arr.append(['total/winning/losing trades', '{}/{}/{}'.format(total, len(winning_trades), len(losing_trades))])
        arr.append(['PNL (%)', '${} ({}%)'.format(pnl, pnl_percentage)])

    if config['app']['debug_mode']:
        arr.append(['debug mode', config['app']['debug_mode']])

    if config['app']['is_test_driving']:
        arr.append(['Test Drive', config['app']['is_test_driving']])
    return arr


def portfolio_metrics() -> List[
    Union[Union[List[Union[str, Any]], List[str], List[Union[Union[str, float], Any]]], Any]]:
    data = stats.trades(store.completed_trades.trades, store.app.daily_balance)

    metrics = [
        ['Total Closed Trades', data['total']],
        ['Total Net Profit',
         '{} ({})'.format(jh.format_currency(round(data['net_profit'], 4)),
                          str(round(data['net_profit_percentage'], 2)) + '%')],
        ['Starting => Finishing Balance',
         '{} => {}'.format(jh.format_currency(round(data['starting_balance'], 2)),
                           jh.format_currency(round(data['finishing_balance'], 2)))],
        ['Total Open Trades', data['total_open_trades']],
        ['Open PL', jh.format_currency(round(data['open_pl'], 2))],
        ['Total Paid Fees', jh.format_currency(round(data['fee'], 2))],
        ['Max Drawdown', '{}%'.format(round(data['max_drawdown'], 2))],
        ['Annual Return', '{}%'.format(round(data['annual_return'], 2))],
        ['Expectancy',
         '{} ({})'.format(jh.format_currency(round(data['expectancy'], 2)),
                          str(round(data['expectancy_percentage'], 2)) + '%')],
        ['Avg Win | Avg Loss', '{} | {}'.format(jh.format_currency(round(data['average_win'], 2)),
                                                jh.format_currency(round(data['average_loss'], 2)))],
        ['Ratio Avg Win / Avg Loss', round(data['ratio_avg_win_loss'], 2)],
        ['Percent Profitable', str(round(data['win_rate'] * 100)) + '%'],
        ['Longs | Shorts', '{}% | {}%'.format(round(data['longs_percentage']), round(data['short_percentage']))],
        ['Avg Holding Time', jh.readable_duration(data['average_holding_period'], 3)],
        ['Winning Trades Avg Holding Time',
         np.nan if np.isnan(data['average_winning_holding_period']) else jh.readable_duration(
             data['average_winning_holding_period'], 3)],
        ['Losing Trades Avg Holding Time',
         np.nan if np.isnan(data['average_losing_holding_period']) else jh.readable_duration(
             data['average_losing_holding_period'], 3)]
    ]

    if jh.get_config('env.metrics.sharpe_ratio', True):
        metrics.append(['Sharpe Ratio', round(data['sharpe_ratio'], 2)])
    if jh.get_config('env.metrics.calmar_ratio', False):
        metrics.append(['Calmar Ratio', round(data['calmar_ratio'], 2)])
    if jh.get_config('env.metrics.sortino_ratio', False):
        metrics.append(['Sortino Ratio', round(data['sortino_ratio'], 2)])
    if jh.get_config('env.metrics.omega_ratio', False):
        metrics.append(['Omega Ratio', round(data['omega_ratio'], 2)])
    if jh.get_config('env.metrics.winning_streak', False):
        metrics.append(['Winning Streak', data['winning_streak']])
    if jh.get_config('env.metrics.losing_streak', False):
        metrics.append(['Losing Streak', data['losing_streak']])
    if jh.get_config('env.metrics.largest_winning_trade', False):
        metrics.append(['Largest Winning Trade', jh.format_currency(round(data['largest_winning_trade'], 2))])
    if jh.get_config('env.metrics.largest_losing_trade', False):
        metrics.append(['Largest Losing Trade', jh.format_currency(round(data['largest_losing_trade'], 2))])
    if jh.get_config('env.metrics.total_winning_trades', False):
        metrics.append(['Total Winning Trades', data['total_winning_trades']])
    if jh.get_config('env.metrics.total_losing_trades', False):
        metrics.append(['Total Losing Trades', data['total_losing_trades']])

    return metrics


def info() -> List[List[Union[str, Any]]]:
    array = []

    for w in store.logs.info[::-1][0:5]:
        array.append(
            [jh.timestamp_to_time(w['time'])[11:19],
             (w['message'][:70] + '..') if len(w['message']) > 70 else w['message']])
    return array


def watch_list() -> Optional[Any]:
    # only support one route
    if len(router.routes) > 1:
        return None

    strategy = router.routes[0].strategy

    # don't if the strategy hasn't been initiated yet
    if not store.candles.is_initiated:
        return None

    watch_list_array = strategy.watch_list()

    return watch_list_array if len(watch_list_array) else None


def errors() -> List[List[Union[str, Any]]]:
    array = []

    for w in store.logs.errors[::-1][0:5]:
        array.append([jh.timestamp_to_time(w['time'])[11:19],
                      (w['message'][:70] + '..') if len(w['message']) > 70 else w['message']])
    return array


def orders() -> List[Union[List[str], List[Union[CharField, str, FloatField]]]]:
    array = []

    # headers
    array.append(['symbol', 'side', 'type', 'qty', 'price', 'flag', 'status', 'created_at'])

    route_orders = []
    for r in router.routes:
        r_orders = store.orders.get_orders(r.exchange, r.symbol)
        for o in r_orders:
            route_orders.append(o)

    if not len(route_orders):
        return None

    route_orders.sort(key=lambda x: x.created_at, reverse=False)

    for o in route_orders[::-1][0:5]:
        array.append([
            o.symbol if o.is_active else jh.color(o.symbol, 'gray'),
            jh.color(o.side, 'red') if o.side == 'sell' else jh.color(o.side, 'green'),
            o.type if o.is_active else jh.color(o.type, 'gray'),
            o.qty if o.is_active else jh.color(str(o.qty), 'gray'),
            o.price if o.is_active else jh.color(str(o.price), 'gray'),
            o.flag if o.is_active else jh.color(o.flag, 'gray'),
            o.status if o.is_active else jh.color(o.status, 'gray'),
            jh.timestamp_to_time(o.created_at)[:19] if o.is_active else jh.color(
                jh.timestamp_to_time(o.created_at)[:19], 'gray'),
        ])
    return array
