import requests

import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.enums import exchanges


class CoinbaseSpot(CandleExchange):
    def __init__(self) -> None:
        # import here instead of the top of the file to prevent possible the circular imports issue
        from jesse.modes.import_candles_mode.drivers.BitfinexSpot import BitfinexSpot

        super().__init__(
            name=exchanges.COINBASE_SPOT,
            count=300,
            rate_limit_per_second=1.5,
            backup_exchange_class=BitfinexSpot
        )

        self.endpoint = 'https://api.pro.coinbase.com/products'

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

    def fetch(self, symbol: str, start_timestamp: int) -> list:
        """
        note1: unlike Bitfinex, Binance does NOT skip candles with volume=0.
        note2: like Bitfinex, start_time includes the candle and so does the end_time.
        """
        end_timestamp = start_timestamp + (self.count - 1) * 60000

        payload = {
            'granularity': '60',
            'start': jh.timestamp_to_time(start_timestamp),
            'end': jh.timestamp_to_time(end_timestamp),
        }

        response = requests.get(
            f"{self.endpoint}/{symbol}/candles",
            params=payload
        )

        self.validate_response(response)

        data = response.json()
        return [{
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': int(d[0]) * 1000,
                'open': float(d[3]),
                'close': float(d[4]),
                'high': float(d[2]),
                'low': float(d[1]),
                'volume': float(d[5])
            } for d in data]
