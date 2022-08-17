import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .bybit_utils import timeframe_to_interval


class BybitUSDTPerpetualMain(CandleExchange):
    def __init__(
            self,
            name: str,
            rest_endpoint: str,
    ) -> None:
        # import here instead of the top of the file to prevent possible the circular imports issue
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(
            name=name,
            count=200,
            rate_limit_per_second=4,
            backup_exchange_class=BinanceSpot
        )

        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': 'W',
            'symbol': dashless_symbol,
            'limit': 200,
            'from': 1514811660
        }

        response = requests.get(self.endpoint + '/public/linear/kline', params=payload)

        self.validate_response(response)

        data = response.json()['result']

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        return int(data[1]['open_time']) * 1000

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        dashless_symbol = jh.dashless_symbol(symbol)
        interval = timeframe_to_interval(timeframe)

        payload = {
            'interval': interval,
            'symbol': dashless_symbol,
            'from': int(start_timestamp / 1000),
            'limit': self.count,
        }

        response = requests.get(self.endpoint + '/public/linear/kline', params=payload)

        self.validate_response(response)

        data = response.json()

        if data['ret_code'] != 0:
            raise exceptions.ExchangeError(data['ret_msg'])

        data = data['result']

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d['open_time']) * 1000,
                'open': float(d['open']),
                'close': float(d['close']),
                'high': float(d['high']),
                'low': float(d['low']),
                'volume': float(d['volume'])
            } for d in data
        ]
