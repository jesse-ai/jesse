from typing import Union

import requests

import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from .lighter_utils import timeframe_to_resolution


class LighterMain(CandleExchange):
    """
    REST candle-import driver for Lighter.

    Note: Lighter only serves a ~130-day rolling window of candles (all resolutions), so
    the exchange is registered with "backtesting": False in jesse/info.py. This driver
    still exists because the live runtime's warm-up candle fetcher calls drivers[name]().

    Docs: https://apidocs.lighter.xyz/reference/candles
          https://apidocs.lighter.xyz/reference/orderbookdetails (symbols + market_id map)
          https://apidocs.lighter.xyz/docs/historical-data
    """

    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinancePerpetualFutures import BinancePerpetualFutures

        # Lighter serves at most 500 candles per /candles request.
        super().__init__(name=name, count=500, rate_limit_per_second=10,
                         backup_exchange_class=BinancePerpetualFutures)
        self.endpoint = rest_endpoint.rstrip('/')
        # symbol (dashy, e.g. 'BTC-USD') -> integer market_id. Lighter displays markets as
        # BASE-USD (collateral is USDC), so we use -USD to match the exchange UI.
        self._market_ids = {}

    def _market_id(self, symbol: str) -> int:
        if not self._market_ids:
            self.get_available_symbols()
        base = jh.get_base_asset(symbol)
        dashy = base + '-USD'
        if dashy not in self._market_ids:
            raise ValueError(f'Symbol "{symbol}" is not listed on {self.name}')
        return self._market_ids[dashy]

    def get_available_symbols(self) -> list:
        response = requests.get(f'{self.endpoint}/api/v1/orderBookDetails')
        self.validate_response(response)
        data = response.json()

        symbols = []
        for market in data.get('order_book_details', []):
            # perp markets only; skip anything not actively trading
            base = market['symbol']
            dashy = base + '-USD'
            self._market_ids[dashy] = int(market['market_id'])
            symbols.append(dashy)

        return list(sorted(symbols))

    def get_starting_time(self, symbol: str) -> int:
        market_id = self._market_id(symbol)
        # Lighter only keeps ~130 days of history; probe from 200 days ago and return the
        # timestamp of the oldest 1m candle it actually serves.
        end = jh.now(force_fresh=True)
        start = end - (200 * 24 * 60 * 60 * 1000)
        params = {
            'market_id': market_id,
            'resolution': '1m',
            'start_timestamp': start,
            'end_timestamp': end,
            'count_back': 500,
        }
        response = requests.get(f'{self.endpoint}/api/v1/candles', params=params)
        self.validate_response(response)
        candles = response.json().get('c', []) or []
        if not candles:
            return start
        # candles are oldest-first; 't' is the open timestamp in ms
        return int(candles[0]['t'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        market_id = self._market_id(symbol)
        resolution = timeframe_to_resolution(timeframe)
        interval_ms = jh.timeframe_to_one_minutes(timeframe) * 60_000
        # request exactly one page (`count` candles) forward from start_timestamp
        end_timestamp = start_timestamp + (self.count - 1) * interval_ms

        params = {
            'market_id': market_id,
            'resolution': resolution,
            'start_timestamp': int(start_timestamp),
            'end_timestamp': int(end_timestamp),
            'count_back': self.count,
        }
        response = requests.get(f'{self.endpoint}/api/v1/candles', params=params)
        self.validate_response(response)
        data = response.json().get('c', []) or []

        # Lighter returns candles oldest-first, timestamps in ms marking the OPEN of the
        # interval (set_timestamp_to_end defaults to false) — no reversal or offset needed.
        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d['t']),
                'open': float(d['o']),
                'close': float(d['c']),
                'high': float(d['h']),
                'low': float(d['l']),
                'volume': float(d['v']),
            }
            for d in data
            if int(d['t']) >= int(start_timestamp)
        ]
