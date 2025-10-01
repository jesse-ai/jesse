from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.services.csv_data_provider import CSVDataProvider
from .csv_parsers import CSVParserFactory
import jesse.helpers as jh
import os
from typing import Optional


class CustomCSV(CandleExchange):
    def __init__(self, data_directory: Optional[str] = None, parser_type: Optional[str] = None, max_candles: int = 1000):
        """
        Initialize CustomCSV driver for local CSV files.
        
        Args:
            data_directory: Path to directory containing CSV data files.
                          If None, uses default KucoinData directory.
            parser_type: Specific CSV parser type to use (optional).
                        If None, auto-detects format.
            max_candles: Maximum number of candles to fetch (default 1000).
                        Set to 0 or None for unlimited.
        """
        super().__init__(
            name='CustomCSV',
            count=max_candles if max_candles else 1000000,  # Large number for unlimited
            rate_limit_per_second=1,
            backup_exchange_class=None
        )
        
        # Set data directory
        if data_directory is None:
            # Try to get from environment variable first
            self.data_directory = os.getenv('CSV_DATA_DIR', "CSVDirectory")
        else:
            self.data_directory = data_directory
            
        # Validate data directory exists
        if not os.path.exists(self.data_directory):
            raise FileNotFoundError(f"Data directory not found: {self.data_directory}")
        
        # Initialize CSV parser using factory
        self.csv_parser = CSVParserFactory.create_parser(self.data_directory, parser_type)
        
        # Initialize CSV data provider with custom directory (for backward compatibility)
        self.csv_provider = CSVDataProvider(data_directory=self.data_directory)
        
        # Cache for symbol info to avoid repeated file system calls
        self._symbol_cache = {}
        self._available_symbols_cache = None

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
            csv_symbol = self._normalize_symbol(symbol)
            
            # Validate symbol exists
            if not self._symbol_exists(csv_symbol):
                raise FileNotFoundError(f'Symbol {symbol} not found in data directory: {self.data_directory}')
            
            # Calculate end timestamp based on timeframe
            end_timestamp = self._calculate_end_timestamp(start_timestamp, timeframe)
            
            # Get candles from CSV parser
            candles = self.csv_parser.get_candles(
                symbol=csv_symbol,
                timeframe=timeframe,
                start_date=start_timestamp,
                finish_date=end_timestamp
            )
            
            if candles is None or len(candles) == 0:
                # Get symbol info to provide more context
                symbol_info = self.csv_parser.get_symbol_info(csv_symbol)
                if symbol_info:
                    start_time_data = symbol_info.get('start_time', 0)
                    end_time = symbol_info.get('end_time', 0)
                    end_date_str = jh.timestamp_to_time(end_time) if end_time else 'Unknown'
                    start_date_str = jh.timestamp_to_time(start_time_data) if start_time_data else 'Unknown'
                    
                    # Determine if data hasn't started yet or has ended
                    if start_timestamp < start_time_data:
                        warning_msg = (
                            f"⚠️  WARNING: No candles found for {symbol} in CSV data for timeframe {timeframe}. "
                            f"Data hasn't started yet. Available data starts: {start_date_str}. "
                            f"Requested start: {jh.timestamp_to_time(start_timestamp)}"
                        )
                    else:
                        warning_msg = (
                            f"⚠️  WARNING: No candles found for {symbol} in CSV data for timeframe {timeframe}. "
                            f"Data may have ended. Last available data: {end_date_str}. "
                            f"Requested start: {jh.timestamp_to_time(start_timestamp)}"
                        )
                    raise Exception(warning_msg)
                else:
                    raise Exception(f'No candles found for {symbol} in CSV data for timeframe {timeframe}')
            
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
            
        except FileNotFoundError as e:
            raise e
        except Exception as e:
            raise Exception(f'Error fetching candles from CSV for {symbol}: {e}')

    def get_starting_time(self, symbol: str) -> int:
        """
        Get starting time for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'ACH' or 'ACH-USDT')
            
        Returns:
            Starting timestamp in milliseconds
        """
        try:
            # Normalize symbol for CSV lookup
            csv_symbol = self._normalize_symbol(symbol)
            
            # Check cache first
            if csv_symbol in self._symbol_cache:
                return self._symbol_cache[csv_symbol]['start_time']
            
            # Get symbol info from CSV parser
            symbol_info = self.csv_parser.get_symbol_info(csv_symbol)
            if symbol_info is None:
                raise FileNotFoundError(f'Symbol {symbol} not found in CSV data directory: {self.data_directory}')
            
            # Cache the symbol info
            self._symbol_cache[csv_symbol] = symbol_info
            
            return symbol_info['start_time']
        except FileNotFoundError as e:
            raise e
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
            # Normalize symbol for CSV lookup
            csv_symbol = self._normalize_symbol(symbol)
            
            # Validate symbol exists
            if not self._symbol_exists(csv_symbol):
                raise FileNotFoundError(f'Symbol {symbol} not found in data directory: {self.data_directory}')
            
            # Get candles from CSV parser
            candles = self.csv_parser.get_candles(
                symbol=csv_symbol,
                timeframe='1m',
                start_date=start_date,
                finish_date=finish_date
            )
            
            if candles is None or len(candles) == 0:
                # Get symbol info to provide more context
                symbol_info = self.csv_parser.get_symbol_info(csv_symbol)
                if symbol_info:
                    end_time = symbol_info.get('end_time', 0)
                    end_date_str = jh.timestamp_to_time(end_time) if end_time else 'Unknown'
                    warning_msg = (
                        f"⚠️  WARNING: No candles found for {symbol} in CSV data between "
                        f"{jh.timestamp_to_time(start_date)} and {jh.timestamp_to_time(finish_date)}. "
                        f"Data may have ended. Last available data: {end_date_str}"
                    )
                    raise Exception(warning_msg)
                else:
                    raise Exception(f'No candles found for {symbol} in CSV data between {start_date} and {finish_date}')
            
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
            
        except FileNotFoundError as e:
            raise e
        except Exception as e:
            raise Exception(f'Error getting candles from CSV for {symbol}: {e}')

    def get_available_symbols(self) -> list:
        """
        Get available symbols from CSV data in SYMBOL-USDT format
        
        Returns:
            List of available symbols in SYMBOL-USDT format
        """
        try:
            # Use cache if available
            if self._available_symbols_cache is not None:
                return self._available_symbols_cache
                
            # Get symbols from CSV parser (already in SYMBOL-USDT format)
            symbols = self.csv_parser.get_available_symbols()
            
            # Cache the result
            self._available_symbols_cache = symbols
            
            return symbols
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
            # Normalize symbol for CSV lookup
            csv_symbol = self._normalize_symbol(symbol)
            
            # Check cache first
            if csv_symbol in self._symbol_cache:
                symbol_info = self._symbol_cache[csv_symbol]
            else:
                symbol_info = self.csv_parser.get_symbol_info(csv_symbol)
                if symbol_info is None:
                    raise FileNotFoundError(f'Symbol {symbol} not found in CSV data directory: {self.data_directory}')
                # Cache the symbol info
                self._symbol_cache[csv_symbol] = symbol_info
            
            return {
                'symbol': symbol,
                'base_asset': csv_symbol,
                'quote_asset': 'USDT',
                'min_qty': 0.001,
                'max_qty': 1000000,
                'step_size': 0.001,
                'tick_size': 0.00001,
                'min_notional': 10.0,
                'price_precision': 5,
                'qty_precision': 3,
                'start_time': symbol_info.get('start_time', 0),
                'end_time': symbol_info.get('end_time', 0)
            }
        except FileNotFoundError as e:
            raise e
        except Exception as e:
            raise Exception(f'Error getting exchange info for {symbol}: {e}')

    def _normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol by removing common suffixes for CSV lookup
        
        Args:
            symbol: Trading symbol (e.g., 'ACH-USDT')
            
        Returns:
            Normalized symbol for CSV lookup (e.g., 'ACH')
        """
        if symbol.endswith('-USDT'):
            return symbol.replace('-USDT', '')
        elif symbol.endswith('-USDC'):
            return symbol.replace('-USDC', '')
        elif symbol.endswith('-BTC'):
            return symbol.replace('-BTC', '')
        elif symbol.endswith('-ETH'):
            return symbol.replace('-ETH', '')
        else:
            return symbol

    def _symbol_exists(self, symbol: str) -> bool:
        """
        Check if symbol exists in data directory
        
        Args:
            symbol: Symbol name (without suffix)
            
        Returns:
            True if symbol exists, False otherwise
        """
        symbol_path = os.path.join(self.data_directory, symbol)
        price_file = os.path.join(symbol_path, "price.csv")
        return os.path.exists(price_file)

    def _calculate_end_timestamp(self, start_timestamp: int, timeframe: str) -> int:
        """
        Calculate end timestamp based on timeframe and count
        
        Args:
            start_timestamp: Start timestamp in milliseconds
            timeframe: Timeframe (e.g., '1m', '5m', '1h')
            
        Returns:
            End timestamp in milliseconds
        """
        # Convert timeframe to milliseconds
        timeframe_ms = self._timeframe_to_ms(timeframe)
        
        # Calculate end timestamp
        return start_timestamp + (self.count - 1) * timeframe_ms

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """
        Convert timeframe string to milliseconds
        
        Args:
            timeframe: Timeframe string (e.g., '1m', '5m', '1h', '1d')
            
        Returns:
            Timeframe in milliseconds
        """
        timeframe_map = {
            '1m': 60 * 1000,      # 1 minute
            '3m': 3 * 60 * 1000,   # 3 minutes
            '5m': 5 * 60 * 1000,   # 5 minutes
            '15m': 15 * 60 * 1000, # 15 minutes
            '30m': 30 * 60 * 1000, # 30 minutes
            '1h': 60 * 60 * 1000,  # 1 hour
            '2h': 2 * 60 * 60 * 1000,  # 2 hours
            '4h': 4 * 60 * 60 * 1000,  # 4 hours
            '6h': 6 * 60 * 60 * 1000,  # 6 hours
            '8h': 8 * 60 * 60 * 1000,  # 8 hours
            '12h': 12 * 60 * 60 * 1000, # 12 hours
            '1d': 24 * 60 * 60 * 1000, # 1 day
        }
        
        return timeframe_map.get(timeframe, 60 * 1000)  # Default to 1 minute

    def clear_cache(self):
        """
        Clear all caches
        """
        self._symbol_cache.clear()
        self._available_symbols_cache = None
        self.csv_parser.clear_cache()
        self.csv_provider.clear_cache()

    def get_data_directory(self) -> str:
        """
        Get the current data directory path
        
        Returns:
            Path to data directory
        """
        return self.data_directory

    def set_data_directory(self, data_directory: str):
        """
        Set a new data directory and reinitialize provider
        
        Args:
            data_directory: New path to data directory
        """
        if not os.path.exists(data_directory):
            raise FileNotFoundError(f"Data directory not found: {data_directory}")
        
        self.data_directory = data_directory
        self.csv_parser = CSVParserFactory.create_parser(self.data_directory)
        self.csv_provider = CSVDataProvider(data_directory=self.data_directory)
        self.clear_cache()
    
    def get_parser_info(self) -> dict:
        """
        Get information about the current CSV parser
        
        Returns:
            Dictionary with parser information
        """
        return self.csv_parser.get_parser_info()
    
    def get_available_parsers(self) -> dict:
        """
        Get list of available CSV parsers
        
        Returns:
            Dictionary mapping parser names to descriptions
        """
        return CSVParserFactory.get_available_parsers()
    
    def set_parser_type(self, parser_type: str):
        """
        Set a specific parser type
        
        Args:
            parser_type: Parser type name
        """
        self.csv_parser = CSVParserFactory.create_parser(self.data_directory, parser_type)
        self.clear_cache()
