import json
import os
import numpy as np
import peewee
import requests

from fastapi.responses import FileResponse
import jesse.helpers as jh


def get_candles(exchange: str, symbol: str, timeframe: str):
    from jesse.services.db import database
    database.open_connection()

    from jesse.services.candle import generate_candle_from_one_minutes
    from jesse.models.utils import fetch_candles_from_db

    symbol = symbol.upper()
    num_candles = 210

    one_min_count = jh.timeframe_to_one_minutes(timeframe)
    finish_date = jh.now(force_fresh=True)
    start_date = finish_date - (num_candles * one_min_count * 60_000)

    # fetch 1m candles from database
    candles = np.array(
        fetch_candles_from_db(exchange, symbol, start_date, finish_date)
    )

    # if there are no candles in the database, return []
    if candles.size == 0:
        database.close_connection()
        return []

    # leave out first candles until the timestamp of the first candle is the beginning of the timeframe
    timeframe_duration = one_min_count*60_000
    while candles[0][0] % timeframe_duration != 0:
        candles = candles[1:]

    # generate bigger candles from 1m candles
    if timeframe != '1m':
        generated_candles = []
        for i in range(len(candles)):
            if (i + 1) % one_min_count == 0:
                bigger_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (one_min_count - 1)):(i + 1)],
                    True
                 )
                generated_candles.append(bigger_candle)

        candles = generated_candles

    database.close_connection()
    
    return [
        {
            'time': int(c[0] / 1000),
            'open': c[1],
            'close': c[2],
            'high': c[3],
            'low': c[4],
            'volume': c[5],
        } for c in candles
    ]


def get_general_info(has_live=False) -> dict:
    from jesse.modes.import_candles_mode.drivers import drivers
    from jesse.version import __version__ as jesse_version
    system_info = {
        'jesse_version': jesse_version
    }

    if has_live:
        from jesse_live.info import SUPPORTED_EXCHANGES_NAMES
        live_exchanges = list(sorted(SUPPORTED_EXCHANGES_NAMES))
        from jesse_live.version import __version__ as live_version
        system_info['live_plugin_version'] = live_version
    else:
        live_exchanges = []

    exchanges = list(sorted(drivers.keys()))
    strategies_path = os.getcwd() + "/strategies/"
    strategies = list(sorted([name for name in os.listdir(strategies_path) if os.path.isdir(strategies_path + name)]))

    system_info['python_version'] = '{}.{}'.format(*jh.python_version())
    system_info['operating_system'] = jh.get_os()
    system_info['cpu_cores'] = jh.cpu_cores_count()
    system_info['is_docker'] = jh.is_docker()

    update_info = {}

    try:
        response = requests.get('https://pypi.org/pypi/jesse/json')
        update_info['jesse_latest_version'] = response.json()['info']['version']
        response = requests.get('https://jesse.trade/api/plugins/live/releases/info')
        update_info['jesse_live_latest_version'] = response.json()[0]['version']
        update_info['is_update_info_available'] = True
    except Exception:
        update_info['is_update_info_available'] = False

    return {
        'exchanges': exchanges,
        'live_exchanges': live_exchanges,
        'strategies': strategies,
        'has_live_plugin_installed': has_live,
        'system_info': system_info,
        'update_info': update_info
    }


def get_config(client_config: dict, has_live=False) -> dict:
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.Option import Option

    try:
        o = Option.get(Option.type == 'config')

        # merge it with client's config (because it could include new keys added),
        # update it in the database, and then return it
        data = jh.merge_dicts(client_config, json.loads(o.json))

        # make sure the list of BACKTEST exchanges is up to date
        from jesse.modes.import_candles_mode.drivers import drivers
        for k in list(data['backtest']['exchanges'].keys()):
            if k not in drivers:
                del data['backtest']['exchanges'][k]

        # make sure the list of LIVE exchanges is up to date
        if has_live:
            from jesse_live.info import SUPPORTED_EXCHANGES_NAMES
            live_exchanges = list(sorted(SUPPORTED_EXCHANGES_NAMES))
            for k in list(data['live']['exchanges'].keys()):
                if k not in live_exchanges:
                    del data['live']['exchanges'][k]

        # fix the settlement_currency of exchanges
        for k, e in data['live']['exchanges'].items():
            e['settlement_currency'] = jh.get_settlement_currency_from_exchange(e['name'])
        for k, e in data['backtest']['exchanges'].items():
            e['settlement_currency'] = jh.get_settlement_currency_from_exchange(e['name'])

        o.updated_at = jh.now()
        o.save()
    except peewee.DoesNotExist:
        # if not found, that means it's the first time. Store in the DB and
        # then return what was sent from the client side without changing it
        o = Option({
            'id': jh.generate_unique_id(),
            'updated_at': jh.now(),
            'type': 'config',
            'json': json.dumps(client_config)
        })
        o.save(force_insert=True)

        data = client_config

    database.close_connection()

    return {
        'data': data
    }


def update_config(client_config: dict):
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.Option import Option

    # at this point there must already be one option record for "config" existing, so:
    o = Option.get(Option.type == 'config')

    o.json = json.dumps(client_config)
    o.updated_at = jh.now()

    o.save()

    database.close_connection()


def download_file(mode: str, file_type: str, session_id: str = None):
    if mode == 'backtest' and file_type == 'log':
        path = f'storage/logs/backtest-mode/{session_id}.txt'
        filename = f'backtest-{session_id}.txt'
    elif mode == 'backtest' and file_type == 'chart':
        path = f'storage/charts/{session_id}.png'
        filename = f'backtest-{session_id}.png'
    elif mode == 'backtest' and file_type == 'csv':
        path = f'storage/csv/{session_id}.csv'
        filename = f'backtest-{session_id}.csv'
    elif mode == 'backtest' and file_type == 'json':
        path = f'storage/json/{session_id}.json'
        filename = f'backtest-{session_id}.json'
    elif mode == 'backtest' and file_type == 'full-reports':
        path = f'storage/full-reports/{session_id}.html'
        filename = f'backtest-{session_id}.html'
    elif mode == 'backtest' and file_type == 'tradingview':
        path = f'storage/trading-view-pine-editor/{session_id}.txt'
        filename = f'backtest-{session_id}.txt'
    elif mode == 'optimize' and file_type == 'log':
        path = f'storage/logs/optimize-mode.txt'
        # filename should be "optimize-" + current timestamp
        filename = f'optimize-{jh.timestamp_to_date(jh.now(True))}.txt'
    else:
        raise Exception(f'Unknown file type: {file_type} or mode: {mode}')

    return FileResponse(path=path, filename=filename, media_type='application/octet-stream')
