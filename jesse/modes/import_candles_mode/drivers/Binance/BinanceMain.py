import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from .binance_utils import timeframe_to_interval


class BinanceMain(CandleExchange):
    def __init__(
            self,
            name: str,
            rest_endpoint: str,
            backup_exchange_class,
    ) -> None:
        super().__init__(
            name=name,
            count=1000,
            rate_limit_per_second=2,
            backup_exchange_class=backup_exchange_class
        )

        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': '1d',
            'symbol': dashless_symbol,
            'limit': 1500,
        }

        response = requests.get(self.endpoint + '/v1/klines', params=payload)

        self.validate_response(response)

        data = response.json()

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        first_timestamp = int(data[0][0])
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        interval = timeframe_to_interval(timeframe)
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': interval,
            'symbol': dashless_symbol,
            'startTime': int(start_timestamp),
            'endTime': int(end_timestamp),
            'limit': self.count,
        }

        response = requests.get(self.endpoint + '/v1/klines', params=payload)

        self.validate_response(response)

        data = response.json()
        return [{
            'id': jh.generate_unique_id(),
            'exchange': self.name,
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': int(d[0]),
            'open': float(d[1]),
            'close': float(d[4]),
            'high': float(d[2]),
            'low': float(d[3]),
            'volume': float(d[5])
        } for d in data]

    def get_available_symbols(self) -> list:
        response = requests.get(self.endpoint + '/v1/exchangeInfo')

        self.validate_response(response)

        data = response.json()

        return [jh.dashy_symbol(d['symbol']) for d in data['symbols']]
