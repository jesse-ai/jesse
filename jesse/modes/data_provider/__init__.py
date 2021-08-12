import json
import os

import numpy as np
import jesse.helpers as jh
from jesse.models import Candle
from jesse.models.Option import Option
from jesse.services.candle import generate_candle_from_one_minutes


def get_candles(exchange: str, symbol: str, timeframe: str):
    exchange = exchange.title()
    symbol = symbol.upper()

    one_min_count = jh.timeframe_to_one_minutes(timeframe)
    finish_date = jh.now(force_fresh=True)
    start_date = finish_date - (210 * one_min_count * 60_000)

    # fetch from database
    candles_tuple = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.timestamp.between(start_date, finish_date),
        Candle.exchange == exchange,
        Candle.symbol == symbol).order_by(Candle.timestamp.asc()).tuples()

    candles = np.array(tuple(candles_tuple))

    if timeframe != '1m':
        generated_candles = []
        for i in range(len(candles)):
            if (i + 1) % one_min_count == 0:
                generated_candles.append(
                    generate_candle_from_one_minutes(
                        timeframe,
                        candles[(i - (one_min_count - 1)):(i + 1)],
                        True
                    )
                )
        candles = generated_candles

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


def available_routes_inputs(has_live=False) -> dict:
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
        'strategies': strategies
    }


def get_config(client_config: dict) -> dict:
    o = Option.get_or_none(Option.type == 'config')

    # if not found, that means it's the first time. Store in the DB and
    # then return what was sent from the client side without changing it
    if o is None:
        o = Option({
            'id': jh.generate_unique_id(),
            'updated_at': jh.now(),
            'type': 'config',
            'json': json.dumps(client_config)
        })
        o.save(force_insert=True)

        data = client_config
    else:
        # merge it with client's config (because it could include new keys added),
        # update it in the database, and then return it
        data = jh.merge_dicts(client_config, json.loads(o.json))
        o.json = json.dumps(data)
        o.updated_at = jh.now()
        o.save()

    return {
        'data': data
    }


def update_config(client_config: dict):
    # at this point there must already be one option record for "config" existing, so:
    o = Option.get_or_none(Option.type == 'config')

    o.json = json.dumps(client_config)
    o.updated_at = jh.now()

    o.save()
