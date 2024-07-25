import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from .dydx_utils import timeframe_to_interval


class DydxPerpetualMain(CandleExchange):
    def __init__(
            self,
            name: str,
            rest_endpoint: str,
            backup_exchange_class
    ) -> None:
        super().__init__(
            name=name,
            count=100,
            rate_limit_per_second=10,
            backup_exchange_class=backup_exchange_class
        )

        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        payload = {
            'resolution': '1DAY',
            'limit': self.count,
            'fromISO': jh.timestamp_to_iso8601(1359291660000),
            'toISO': jh.timestamp_to_iso8601(jh.now_to_timestamp(force_fresh=True))
        }

        response = requests.get(self.endpoint + '/v3/candles/' + symbol, params=payload)

        self.validate_response(response)

        data = response.json()['candles']

        # reverse items of the list
        data.reverse()

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        return jh.iso8601_to_timestamp(data[1]['startedAt'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        start_timestamp = start_timestamp - 60000
        payload = {
            'resolution': timeframe_to_interval(timeframe),
            'fromISO': jh.timestamp_to_iso8601(start_timestamp),
            'limit': self.count,
            'toISO': jh.timestamp_to_iso8601(end_timestamp)
        }

        response = requests.get(self.endpoint + '/v3/candles/' + symbol, params=payload)

        self.validate_response(response)
        data = response.json()['candles']

        # reverse items of the list
        data.reverse()

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': jh.iso8601_to_timestamp(d['startedAt']),
                'open': float(d['open']),
                'close': float(d['close']),
                'high': float(d['high']),
                'low': float(d['low']),
                'volume': float(d['baseTokenVolume'])
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = requests.get(self.endpoint + '/v3/markets')
        self.validate_response(response)
        data = response.json()['markets']

        return [k for k, s in data.items()]
