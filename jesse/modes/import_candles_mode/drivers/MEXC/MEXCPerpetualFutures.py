import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.enums import exchanges
from .mexc_utils import timeframe_to_interval


class MEXCPerpetualFutures(CandleExchange):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.MEXC_PERPETUAL_FUTURES,
            count=2000,
            rate_limit_per_second=10,
            backup_exchange_class=None
        )

        self.endpoint = 'https://contract.mexc.com/api/v1/contract'

    def get_starting_time(self, symbol: str) -> int:
        if symbol == 'BTC-USD':
            return 1438387200000
        elif symbol == 'ETH-USD':
            return 1464739200000
        elif symbol == 'LTC-USD':
            return 1477958400000

        return None

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str) -> list:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)

        payload = {
            'interval': timeframe_to_interval(timeframe),
            'start': int(start_timestamp / 1000),
            'end': int(end_timestamp / 1000),
        }

        response = requests.get(
            f"{self.endpoint}/kline/{jh.dashy_to_underline(symbol)}",
            params=payload
        )

        self.validate_response(response)

        data = response.json()['data']
        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(data['time'][i]) * 1000,
                'open': float(data['open'][i]),
                'close': float(data['close'][i]),
                'high': float(data['high'][i]),
                'low': float(data['low'][i]),
                'volume': float(data['vol'][i])
            } for i in range(len(data['time']))
        ]

    def get_available_symbols(self) -> list:
        response = requests.get(f"{self.endpoint}/detail")
        self.validate_response(response)
        data = response.json()['data']
        available_symbols = []
        for s in data:
            jh.dump(jh.underline_to_dashy_symbol(s['symbol']))
            available_symbols.append(jh.underline_to_dashy_symbol(s['symbol']))

        return available_symbols
