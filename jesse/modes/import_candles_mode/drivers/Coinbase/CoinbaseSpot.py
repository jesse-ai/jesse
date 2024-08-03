import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.enums import exchanges
from .coinbase_utils import timeframe_to_interval


class CoinbaseSpot(CandleExchange):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.COINBASE_SPOT,
            count=300,
            rate_limit_per_second=1.5,
            backup_exchange_class=None
        )

        self.endpoint = 'https://api.coinbase.com/api/v3/brokerage/market/products'

    def get_starting_time(self, symbol: str) -> int:
        """
        Because Coinbase's API sucks and does not make this take easy for us,
        we do it manually for as much symbol as we can!

        :param symbol: str
        :return: int
        """
        if symbol == 'BTC-USD':
            return 1438387200000
        elif symbol == 'ETH-USD':
            return 1464739200000
        elif symbol == 'LTC-USD':
            return 1477958400000

        return None

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str) -> list:
        """
        note1: unlike Bitfinex, Binance does NOT skip candles with volume=0.
        note2: like Bitfinex, start_time includes the candle and so does the end_time.
        """
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)

        payload = {
            'granularity': timeframe_to_interval(timeframe),
            'start': int(start_timestamp / 1000),
            'end': int(end_timestamp / 1000),
        }

        response = requests.get(
            f"{self.endpoint}/{symbol}/candles",
            params=payload
        )

        self.validate_response(response)

        data = response.json()['candles']
        data = data[::-1]
        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d['start']) * 1000,
                'open': float(d['open']),
                'close': float(d['close']),
                'high': float(d['high']),
                'low': float(d['low']),
                'volume': float(d['volume'])
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = requests.get(self.endpoint)
        self.validate_response(response)
        data = response.json()['products']
        available_symbols = []
        for s in data:
            if len(s['alias_to']) == 0:
                available_symbols.append(s['product_id'])

        return available_symbols
