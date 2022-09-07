from typing import Union
import requests
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.enums import exchanges
from .bitget_utils import timeframe_to_interval, jesse_symbol_to_bitget_usdt_contracts_symbol
import jesse.helpers as jh


class BitgetUSDTPerpetualMain(CandleExchange):
    def __init__(
            self,
            name: str,
            endpoint: str,
    ) -> None:
        super().__init__(
            name=name,
            count=100,
            rate_limit_per_second=18,
            backup_exchange_class=None
        )

        self.endpoint = endpoint

    def get_starting_time(self, symbol: str) -> int:
        payload = {
            'granularity': '1W',
            'symbol': jesse_symbol_to_bitget_usdt_contracts_symbol(symbol),
            'startTime': 1359291660000,
            'endTime': jh.now(force_fresh=True)
        }

        response = requests.get(self.endpoint, params=payload)

        self.validate_response(response)

        data = response.json()

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        return int(data[1][0])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)

        payload = {
            'granularity': timeframe_to_interval(timeframe),
            'symbol': jesse_symbol_to_bitget_usdt_contracts_symbol(symbol),
            'startTime': int(start_timestamp),
            'endTime': int(end_timestamp)
        }

        response = requests.get(self.endpoint, params=payload)

        self.validate_response(response)

        data = response.json()

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d[0]),
                'open': float(d[1]),
                'high': float(d[2]),
                'low': float(d[3]),
                'close': float(d[4]),
                'volume': float(d[5])
            } for d in data
        ]
