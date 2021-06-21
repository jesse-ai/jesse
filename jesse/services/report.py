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
        p: Position = r.strategy.position
        arr.append({
            'type': p.type,
            'strategy_name': p.strategy.name,
            'symbol': p.symbol,
            'leverage': p.leverage,
            'opened_at': p.opened_at,
            'qty': p.qty,
            'entry': p.entry_price,
            'current_price': p.current_price,
            'liq_price': p.liquidation_price,
            'pnl': p.pnl,
            'pnl_perc': p.pnl_percentage
        })

    return arr

    array = []

    # headers
    array.append([
        'type', 'strategy', 'symbol', 'leverage', 'opened at', 'qty', 'entry', 'current price', 'liq price', 'PNL (%)'
    ])

    for r in router.routes:
        pos = r.strategy.position

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
                pos.leverage,
                '' if pos.is_close else f'{jh.readable_duration((jh.now_to_timestamp() - pos.opened_at) / 1000, 3)} ago',
                pos.qty if abs(pos.qty) > 0 else None,
                pos.entry_price,
                pos.current_price,
                '' if (np.isnan(pos.liquidation_price) or pos.liquidation_price == 0) else pos.liquidation_price,
                '' if pos.is_close else f'{jh.color(str(round(pos.pnl, 2)), pnl_color)} ({jh.color(str(round(pos.pnl_percentage, 4)), pnl_color)}%)',
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


def livetrade():
    # TODO: for now, we assume that we trade on one exchange only. Later, we need to support for more than one exchange at a time
    # sum up balance of all trading exchanges
    starting_balance = 0
    current_balance = 0
    for e in store.exchanges.storage:
        starting_balance += store.exchanges.storage[e].starting_assets[jh.app_currency()]
        current_balance += store.exchanges.storage[e].assets[jh.app_currency()]
    starting_balance = round(starting_balance, 2)
    current_balance = round(current_balance, 2)

    # short trades summary
    if len(store.completed_trades.trades):
        df = pd.DataFrame.from_records([t.to_dict() for t in store.completed_trades.trades])
        total = len(df)
        winning_trades = len(df.loc[df['PNL'] > 0])
        losing_trades = len(df.loc[df['PNL'] < 0])
        pnl = round(df['PNL'].sum(), 2)
        pnl_perc = round((pnl / starting_balance) * 100, 2)
    else:
        pnl, pnl_perc, total, winning_trades, losing_trades = 0, 0, 0, 0, 0

    return {
        'started_at': store.app.starting_time,
        'current_time': jh.now_to_timestamp(),
        'started_balance': starting_balance,
        'current_balance': current_balance,
        'debug_mode': config['app']['debug_mode'],
        'count_error_logs': len(store.logs.errors),
        'count_info_logs': len(store.logs.info),
        'count_active_orders': store.orders.count_all_active_orders(),
        'open_positions': store.positions.count_open_positions(),
        'pnl': pnl,
        'pnl_perc': pnl_perc,
        'count_trades': total,
        'count_winning_trades': winning_trades,
        'count_losing_trades': losing_trades,
    }


def portfolio_metrics() -> dict:
    return stats.trades(store.completed_trades.trades, store.app.daily_balance)


def info() -> List[List[Union[str, Any]]]:
    array = []

    for w in store.logs.info[::-1][0:5]:
        array.append(
            [
                jh.timestamp_to_time(w['time'])[11:19],
                f"{w['message'][:70]}.." if len(w['message']) > 70 else w['message']
            ])
    return array


def watch_list() -> Optional[Any]:
    # only support one route
    if len(router.routes) > 1:
        return None

    strategy = router.routes[0].strategy

    # don't if the strategy hasn't been initiated yet
    if not store.candles.are_all_initiated:
        return None

    watch_list_array = strategy.watch_list()

    return watch_list_array if len(watch_list_array) else None


def errors() -> List[List[Union[str, Any]]]:
    array = []

    for w in store.logs.errors[::-1][0:5]:
        array.append([jh.timestamp_to_time(w['time'])[11:19],
                      f"{w['message'][:70]}.." if len(w['message']) > 70 else w['message']])
    return array


def orders():
    arr = []

    route_orders = []
    for r in router.routes:
        r_orders = store.orders.get_orders(r.exchange, r.symbol)
        for o in r_orders:
            route_orders.append(o)

    if not len(route_orders):
        return []

    route_orders.sort(key=lambda x: x.created_at, reverse=False)

    for o in route_orders[::-1][0:5]:
        arr.append({
            'symbol': o.symbol,
            'side': o.side,
            'type': o.type,
            'qty': o.qty,
            'price': o.price,
            'flag': o.flag,
            'status': o.status,
            'created_at': o.created_at,
            'canceled_at': o.canceled_at,
            'executed_at': o.executed_at,
        })

    return arr
