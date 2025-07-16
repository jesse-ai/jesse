import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.Bitunix.bitunix_utils import timeframe_to_interval


class BitunixMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(name=name, count=200, rate_limit_per_second=10, backup_exchange_class=BinanceSpot)
        self.name = name
        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)
        payload = {
            'symbol': dashless_symbol,
            'interval': '1w',
            'limit': 200
        }

        response = requests.get(self.endpoint + '/market/kline', params=payload)
        self.validate_response(response)

        if 'data' not in response.json():
            raise exceptions.ExchangeInMaintenance(response.json()['msg'])
        elif response.json()['data'] == {}:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = response.json()['data']

        # Reverse the data list
        data = data[::-1]
        return int(data[1]['time'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        dashless_symbol = jh.dashless_symbol(symbol)
        interval = timeframe_to_interval(timeframe)
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        payload = {
            'symbol': dashless_symbol,
            'interval': interval,
            'startTime': int(start_timestamp),
            'endTime': int(end_timestamp) + 60 * 1000,
            'limit': self.count
        }

        response = requests.get(self.endpoint + '/market/kline', params=payload)
        # check data exist in response.json

        if 'data' not in response.json():
            raise exceptions.ExchangeInMaintenance(response.json()['msg'])
        elif response.json()['data'] == {}:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = response.json()['data']
        data = data[::-1]

        candles = [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d['time']),
                'open': float(d['open']),
                'close': float(d['close']),
                'high': float(d['high']),
                'low': float(d['low']),
                'volume': float(d['baseVol'])
            } for d in data
        ]

        # if the last candle is not the most recent candle, generate the next candle
        if candles[-1]['timestamp'] + (jh.timeframe_to_one_minutes(timeframe) * 60_000 * 2) > jh.now():
            if (candles[-1]['timestamp'] + jh.timeframe_to_one_minutes(timeframe) * 60_000 < jh.now()):
                candles.append(
                    {
                        'id': jh.generate_unique_id(),
                        'exchange': self.name,
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'timestamp': candles[-1]['timestamp'] + jh.timeframe_to_one_minutes(timeframe) * 60_000,
                        'open': float(candles[-1]['close']),
                        'close': float(candles[-1]['close']),
                        'high': float(candles[-1]['close']),
                        'low': float(candles[-1]['close']),
                        'volume': float(candles[-1]['volume'])
                    }
                )
        return candles

    def get_available_symbols(self) -> list:
        response = requests.get(self.endpoint + '/market/trading_pairs')
        self.validate_response(response)
        data = response.json()['data']

        symbols = []
        for p in data:
            symbol = jh.dashy_symbol(p['symbol'])
            symbols.append(symbol)

        return list(sorted(symbols))
