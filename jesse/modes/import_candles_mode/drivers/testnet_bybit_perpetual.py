import requests

import jesse.helpers as jh
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union

class TestnetBybitPerpetual(CandleExchange):
    def __init__(self) -> None:
        # import here instead of the top of the file to prevent possible the circular imports issue
        from jesse.modes.import_candles_mode.drivers.binance import Binance

        super().__init__(
            name='Testnet Bybit Perpetual',
            count=200,
            rate_limit_per_second=4,
            backup_exchange_class=Binance
        )

        self.endpoint = 'https://api-testnet.bybit.com/public/linear/kline'

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': 'W',
            'symbol': dashless_symbol,
            'limit': 200,
            'from': 1514811660
        }

        response = requests.get(self.endpoint, params=payload)

        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')

        # unsupported symbol
        if response.status_code == 400:
            raise ValueError(response.json()['msg'])

        if response.status_code != 200:
            raise Exception(response.content)

        data = response.json()['result']

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        return int(data[1]['open_time']) * 1000

    def fetch(self, symbol: str, start_timestamp: int) -> Union[list, None]:
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': 1,
            'symbol': dashless_symbol,
            'from': int(start_timestamp / 1000),
            'limit': self.count,
        }

        response = requests.get(self.endpoint, params=payload)

        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')

        # unsupported symbol
        if response.status_code == 400:
            raise ValueError(response.json()['msg'])

        if response.status_code != 200:
            return

        data = response.json()['result']

        return [{
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': int(d['open_time']) * 1000,
                'open': float(d['open']),
                'close': float(d['close']),
                'high': float(d['high']),
                'low': float(d['low']),
                'volume': float(d['volume'])
            } for d in data]
