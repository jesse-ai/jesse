import ccxt
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from .kucoin_utils import timeframe_to_interval
import time


class KuCoinMain(CandleExchange):
    def __init__(
            self,
            name: str,
            rest_endpoint: str,
            backup_exchange_class,
    ) -> None:
        super().__init__(
            name=name,
            count=1500,  # KuCoin allows up to 1500 candles per request
            rate_limit_per_second=10,  # KuCoin rate limit
            backup_exchange_class=backup_exchange_class
        )

        self.endpoint = rest_endpoint
        # Initialize CCXT exchange
        self.exchange = ccxt.kucoin({
            'apiKey': '',  # No API key needed for public data
            'secret': '',
            'password': '',
            'sandbox': 'testnet' in name.lower(),
            'enableRateLimit': True,
            'timeout': 30000,
        })

    def _convert_timeframe(self, timeframe: str) -> str:
        """Convert Jesse timeframe to CCXT timeframe format"""
        timeframe_map = {
            '1m': '1m',
            '3m': '3m', 
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1h',
            '2h': '2h',
            '4h': '4h',
            '6h': '6h',
            '8h': '8h',
            '12h': '12h',
            '1D': '1d',
            '1W': '1w',
            '1M': '1M'
        }
        
        if timeframe not in timeframe_map:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        
        return timeframe_map[timeframe]

    def _convert_symbol(self, symbol: str) -> str:
        """Convert Jesse symbol format to CCXT format"""
        # Jesse uses BTC-USDT, CCXT uses BTC/USDT
        return symbol.replace('-', '/')

    def get_starting_time(self, symbol: str) -> int:
        """
        Get the earliest available timestamp for a symbol
        """
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            
            # Try to get data from a reasonable start date (2020-01-01)
            start_date = 1577836800000  # 2020-01-01 00:00:00 UTC
            
            # Get the earliest available data
            ohlcv = self.exchange.fetch_ohlcv(
                ccxt_symbol, 
                '1d', 
                since=start_date, 
                limit=1
            )
            
            if not ohlcv:
                # If no data from 2020, try from 2017
                start_date = 1483228800000  # 2017-01-01 00:00:00 UTC
                ohlcv = self.exchange.fetch_ohlcv(
                    ccxt_symbol, 
                    '1d', 
                    since=start_date, 
                    limit=1
                )
            
            if not ohlcv:
                raise ValueError(f"No data available for symbol {symbol}")
            
            # Get the first available timestamp
            first_timestamp = ohlcv[0][0]
            # Add one day to ensure we have complete 1m data
            return first_timestamp + 60_000 * 1440
            
        except Exception as e:
            # If all else fails, return a reasonable default
            print(f"Warning: Could not get starting time for {symbol}: {str(e)}")
            return 1577836800000  # 2020-01-01 00:00:00 UTC

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            ccxt_timeframe = self._convert_timeframe(timeframe)
            
            # Calculate end timestamp
            end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
            
            # Fetch OHLCV data
            ohlcv = self.exchange.fetch_ohlcv(
                ccxt_symbol,
                ccxt_timeframe,
                since=start_timestamp,
                limit=self.count
            )
            
            if not ohlcv:
                return []
            
            # Convert to Jesse format
            candles = []
            for candle in ohlcv:
                candles.append({
                    'id': jh.generate_unique_id(),
                    'exchange': self.name,
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'timestamp': int(candle[0]),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5])
                })
            
            return candles
            
        except Exception as e:
            print(f"Error fetching candles for {symbol}: {str(e)}")
            return []

    def get_available_symbols(self) -> list:
        try:
            markets = self.exchange.load_markets()
            
            # Filter only trading symbols
            trading_symbols = []
            for symbol, market in markets.items():
                if market.get('active', False) and market.get('type') == 'spot':
                    # Convert from CCXT format (BTC/USDT) to Jesse format (BTC-USDT)
                    jesse_symbol = symbol.replace('/', '-')
                    trading_symbols.append(jesse_symbol)
            
            return trading_symbols
            
        except Exception as e:
            print(f"Error getting available symbols: {str(e)}")
            return []

    def __del__(self):
        """Cleanup method"""
        if hasattr(self, 'exchange'):
            try:
                self.exchange.close()
            except:
                pass