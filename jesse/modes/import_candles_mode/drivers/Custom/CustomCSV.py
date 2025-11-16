from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.services.csv_data_provider import csv_data_provider
import jesse.helpers as jh


class CustomCSV(CandleExchange):
    def __init__(self):
        super().__init__(
            name='CustomCSV',
            count=1000,
            rate_limit_per_second=1,
            backup_exchange_class=None
        )

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str) -> list:
        """
        Fetch candles from CSV data provider
        
        Args:
            symbol: Trading symbol (e.g., 'ACH' or 'ACH-USDT')
            start_timestamp: Start timestamp in milliseconds
            timeframe: Timeframe (e.g., '1m')
            
        Returns:
            List of candles in Jesse format
        """
        try:
            # Remove common suffixes from symbol for CSV lookup
            csv_symbol = symbol
            if symbol.endswith('-USDT'):
                csv_symbol = symbol.replace('-USDT', '')
            elif symbol.endswith('-USDC'):
                csv_symbol = symbol.replace('-USDC', '')
            elif symbol.endswith('-BTC'):
                csv_symbol = symbol.replace('-BTC', '')
            elif symbol.endswith('-ETH'):
                csv_symbol = symbol.replace('-ETH', '')
            
            # Get candles from CSV data provider
            candles = csv_data_provider.get_candles(
                symbol=csv_symbol,
                timeframe=timeframe,
                start_date=start_timestamp,
                finish_date=start_timestamp + (self.count - 1) * 60000  # Calculate end timestamp
            )
            
            if candles is None or len(candles) == 0:
                raise Exception(f'No candles found for {symbol} in CSV data')
            
            # Convert to Jesse format (list of dictionaries)
            jesse_candles = []
            for candle in candles:
                jesse_candles.append({
                    'id': jh.generate_unique_id(),  # id
                    'timestamp': int(candle[0]),    # timestamp
                    'open': float(candle[1]),       # open
                    'close': float(candle[2]),      # close
                    'high': float(candle[3]),       # high
                    'low': float(candle[4]),        # low
                    'volume': float(candle[5]),     # volume
                    'symbol': symbol,               # symbol
                    'exchange': 'CustomCSV',       # exchange
                    'timeframe': timeframe          # timeframe
                })
            
            return jesse_candles
            
        except Exception as e:
            raise Exception(f'Error fetching candles from CSV: {e}')

    def get_starting_time(self, symbol: str) -> int:
        """
        Get starting time for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'ACH' or 'ACH-USDT')
            
        Returns:
            Starting timestamp in milliseconds
        """
        try:
            # Remove common suffixes from symbol for CSV lookup
            csv_symbol = symbol
            if symbol.endswith('-USDT'):
                csv_symbol = symbol.replace('-USDT', '')
            elif symbol.endswith('-USDC'):
                csv_symbol = symbol.replace('-USDC', '')
            elif symbol.endswith('-BTC'):
                csv_symbol = symbol.replace('-BTC', '')
            elif symbol.endswith('-ETH'):
                csv_symbol = symbol.replace('-ETH', '')
            
            symbol_info = csv_data_provider.get_symbol_info(csv_symbol)
            if symbol_info is None:
                raise Exception(f'Symbol {symbol} not found in CSV data')
            
            return symbol_info['start_time']
        except Exception as e:
            raise Exception(f'Error getting starting time for {symbol}: {e}')

    def get_candles(self, symbol: str, start_date: int, finish_date: int) -> list:
        """
        Get candles from CSV data provider
        
        Args:
            symbol: Trading symbol (e.g., 'ACH' or 'ACH-USDT')
            start_date: Start timestamp in milliseconds
            finish_date: Finish timestamp in milliseconds
            
        Returns:
            List of candles in Jesse format
        """
        try:
            # Remove common suffixes from symbol for CSV lookup
            csv_symbol = symbol
            if symbol.endswith('-USDT'):
                csv_symbol = symbol.replace('-USDT', '')
            elif symbol.endswith('-USDC'):
                csv_symbol = symbol.replace('-USDC', '')
            elif symbol.endswith('-BTC'):
                csv_symbol = symbol.replace('-BTC', '')
            elif symbol.endswith('-ETH'):
                csv_symbol = symbol.replace('-ETH', '')
            
            # Get candles from CSV data provider
            candles = csv_data_provider.get_candles(
                symbol=csv_symbol,
                timeframe='1m',
                start_date=start_date,
                finish_date=finish_date
            )
            
            if candles is None or len(candles) == 0:
                raise Exception(f'No candles found for {symbol} in CSV data')
            
            # Convert to Jesse format (list of dictionaries)
            jesse_candles = []
            for candle in candles:
                jesse_candles.append({
                    'id': jh.generate_unique_id(),  # id
                    'timestamp': int(candle[0]),    # timestamp
                    'open': float(candle[1]),       # open
                    'close': float(candle[2]),      # close
                    'high': float(candle[3]),       # high
                    'low': float(candle[4]),        # low
                    'volume': float(candle[5]),     # volume
                    'symbol': symbol,               # symbol
                    'exchange': 'CustomCSV',       # exchange
                    'timeframe': '1m'               # timeframe (hardcoded for get_candles)
                })
            
            return jesse_candles
            
        except Exception as e:
            raise Exception(f'Error getting candles from CSV: {e}')

    def get_available_symbols(self) -> list:
        """
        Get available symbols from CSV data in SYMBOL-USDT format
        
        Returns:
            List of available symbols in SYMBOL-USDT format
        """
        try:
            # Get symbols from CSV data provider (already in SYMBOL-USDT format)
            return csv_data_provider.get_available_symbols()
        except Exception as e:
            raise Exception(f'Error getting symbols from CSV: {e}')

    def get_exchange_info(self, symbol: str) -> dict:
        """
        Get exchange info for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with exchange info
        """
        try:
            symbol_info = csv_data_provider.get_symbol_info(symbol)
            if symbol_info is None:
                raise Exception(f'Symbol {symbol} not found in CSV data')
            
            return {
                'symbol': symbol,
                'base_asset': symbol,
                'quote_asset': 'USDT',
                'min_qty': 0.001,
                'max_qty': 1000000,
                'step_size': 0.001,
                'tick_size': 0.00001,
                'min_notional': 10.0,
                'price_precision': 5,
                'qty_precision': 3
            }
        except Exception as e:
            raise Exception(f'Error getting exchange info for {symbol}: {e}')
