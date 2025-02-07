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
from jesse.models import Position

warnings.filterwarnings("ignore")


def positions() -> list:
    arr = []

    for r in router.routes:
        if r.strategy is None:
            continue
        p: Position = r.strategy.position
        arr.append({
            'currency': jh.app_currency(),
            'type': p.type,
            'strategy_name': p.strategy.name,
            'symbol': p.symbol,
            'leverage': p.leverage,
            'opened_at': p.opened_at,
            'qty': p.qty,
            'value': p.value,
            'entry': p.entry_price,
            'current_price': p.current_price,
            'liquidation_price': p.liquidation_price,
            'pnl': p.pnl,
            'pnl_perc': p.pnl_percentage
        })

    return arr


def candles() -> dict:
    candles_dict = {}
    candle_keys = []

    # add routes
    for e in router.routes:
        if e.strategy is None:
            return {}

        candle_keys.append({
            'exchange': e.exchange,
            'symbol': e.symbol,
            'timeframe': e.timeframe
        })

    # # add data_routes
    # for e in router.data_candles:
    #     candle_keys.append({
    #         'exchange': e['exchange'],
    #         'symbol': e['symbol'],
    #         'timeframe': e['timeframe']
    #     })

    for k in candle_keys:
        try:
            c = store.candles.get_current_candle(k['exchange'], k['symbol'], k['timeframe'])
            key = jh.key(k['exchange'], k['symbol'], k['timeframe'])
            candles_dict[key] = {
                'time': int(c[0] / 1000),
                'open': c[1],
                'close': c[2],
                'high': c[3],
                'low': c[4],
                'volume': c[5],
            }
        except IndexError:
            return {}
        except Exception:
            raise

    return candles_dict


def livetrade():
    starting_balance = 0
    current_balance = 0
    exchange_name = ''
    leverage = 1
    leverage_type = 'spot'
    available_margin = 0
    for e in store.exchanges.storage:
        starting_balance = round(store.exchanges.storage[e].started_balance, 2)
        current_balance = round(store.exchanges.storage[e].wallet_balance, 2)
        exchange_name = e
        if store.exchanges.storage[e].type == 'futures':
            leverage = store.exchanges.storage[e].futures_leverage
            leverage_type = store.exchanges.storage[e].futures_leverage_mode
            available_margin = round(store.exchanges.storage[e].available_margin, 2)
        # there's only one exchange, so we can break
        break

    # short trades summary
    if len(store.completed_trades.trades):
        df = pd.DataFrame.from_records([t.to_dict for t in store.completed_trades.trades])
        total = len(df)
        winning_trades = len(df.loc[df['PNL'] > 0])
        losing_trades = len(df.loc[df['PNL'] < 0])
        pnl = round(df['PNL'].sum(), 2)
        pnl_perc = round((pnl / starting_balance) * 100, 2)
    else:
        pnl, pnl_perc, total, winning_trades, losing_trades = 0, 0, 0, 0, 0

    routes = [
        {
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'strategy': r.strategy_name
        } for r in router.routes
    ]

    return {
        'session_id': store.app.session_id,
        'started_at': str(store.app.starting_time),
        'current_time': str(jh.now_to_timestamp()),
        'started_balance': str(starting_balance),
        'current_balance': str(current_balance),
        'debug_mode': str(config['app']['debug_mode']),
        'paper_mode': str(jh.is_paper_trading()),
        'count_error_logs': str(len(store.logs.errors)),
        'count_info_logs': str(len(store.logs.info)),
        'count_active_orders': str(store.orders.count_all_active_orders()),
        'open_positions': str(store.positions.count_open_positions()),
        'pnl': str(pnl),
        'pnl_perc': str(pnl_perc),
        'count_trades': str(total),
        'count_winning_trades': str(winning_trades),
        'count_losing_trades': str(losing_trades),
        'routes': routes,
        'exchange': exchange_name,
        'leverage': leverage,
        "leverage_type": leverage_type,
        'available_margin': available_margin
    }


def portfolio_metrics() -> Union[dict, None]:
    if store.completed_trades.count == 0:
        return None

    return stats.trades(store.completed_trades.trades, store.app.daily_balance)


def trades() -> List[dict]:
    if store.completed_trades.count == 0:
        return []
    return [t.to_dict_with_orders for t in store.completed_trades.trades]


def info() -> List[List[Union[str, Any]]]:
    return [
        [
            jh.timestamp_to_time(w['time'])[11:19],
            f"{w['message'][:70]}.."
            if len(w['message']) > 70
            else w['message'],
        ]
        for w in store.logs.info[::-1][0:5]
    ]


def watch_list() -> List[List[Union[str, str]]]:
    """
    Returns a list of data that are currently being watched in realtime
    only support the first route
    """
    strategy = router.routes[0].strategy

    # return if strategy object is not initialized yet
    if strategy is None:
        return []

    # don't if the strategy hasn't been initiated yet
    if not store.candles.are_all_initiated:
        return []

    try:
        watch_list_array = strategy.watch_list()
    except Exception as e:
        import traceback

        watch_list_array = [
            ('', "The watch list is not available because an error occurred while getting it. Please check your strategy code's watch_list() method."),
            ('', f'ERROR: ```{traceback.format_exc()}```')
        ]

    # loop through the watch list and convert each item into a string
    for index, value in enumerate(watch_list_array):
        # if value is not a tuple with two values in it, raise ValueError
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValueError("watch_list() must return a list of tuples with 2 values in each. Example: [(key1, value1), (key2, value2)]")

        watch_list_array[index] = (str(value[0]), str(value[1]))

    return watch_list_array if len(watch_list_array) else []


def errors() -> List[List[Union[str, Any]]]:
    return [
        [
            jh.timestamp_to_time(w['time'])[11:19],
            f"{w['message'][:70]}.."
            if len(w['message']) > 70
            else w['message'],
        ]
        for w in store.logs.errors[::-1][0:5]
    ]


def orders() -> List[dict]:
    route_orders = []

    for r in router.routes:
        r_orders = store.orders.get_orders(r.exchange, r.symbol)
        for o in r_orders:
            route_orders.append(o.to_dict)

    return route_orders
