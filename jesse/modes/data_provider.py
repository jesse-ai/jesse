import json
import os
import numpy as np
import peewee

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

    # fetch from database
    candles = np.array(
        fetch_candles_from_db(exchange, symbol, start_date, finish_date)
    )

    if timeframe != '1m':
        generated_candles = [generate_candle_from_one_minutes(
                        timeframe,
                        candles[(i - (one_min_count - 1)):(i + 1)],
                        True
                    ) for i in range(len(candles)) if (i + 1) % one_min_count == 0]
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

    if has_live:
        from jesse_live.info import SUPPORTED_EXCHANGES_NAMES
        live_exchanges = list(sorted(SUPPORTED_EXCHANGES_NAMES))
    else:
        live_exchanges = []

    exchanges = list(sorted(drivers.keys()))
    strategies_path = os.getcwd() + "/strategies/"
    strategies = list(sorted([name for name in os.listdir(strategies_path) if os.path.isdir(strategies_path + name)]))

    return {
        'exchanges': exchanges,
        'live_exchanges': live_exchanges,
        'strategies': strategies,
        'has_live_plugin_installed': has_live,
        'cpu_cores': jh.cpu_cores_count()
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


def download_file(mode: str, file_type: str, session_id: str):
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
    else:
        raise Exception(f'Unknown file type: {file_type} or mode: {mode}')

    return FileResponse(path=path, filename=filename, media_type='application/octet-stream')
