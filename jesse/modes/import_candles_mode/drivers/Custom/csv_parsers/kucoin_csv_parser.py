"""
Kucoin CSV Parser implementation for CustomCSV driver.

This parser handles the specific CSV format used by KucoinData:
- File structure: SYMBOL/price.csv
- CSV format: t,p,v (timestamp, price, volume)
- Headers: t,p,v
"""

import os
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from .base_csv_parser import BaseCSVParser
from jesse.services import logger


class KucoinCSVParser(BaseCSVParser):
    """
    CSV parser for KucoinData format.
    
    Expected file structure:
    /data_directory/
    ├── ACH/
    │   └── price.csv
    ├── AEG/
    │   └── price.csv
    └── ...
    
    CSV format:
    t,p,v
    1672444800000,0.00785,0.0
    1672444800001,0.00785,0.0
    """
    
    def __init__(self, data_directory: str = "/Users/alxy/Downloads/Fond/KucoinData"):
        """
        Initialize Kucoin CSV parser.
        
        Args:
            data_directory: Base directory containing CSV data files
        """
        super().__init__(data_directory)
        self.expected_columns = ['t', 'p', 'v']  # timestamp, price, volume
        self.expected_headers = 't,p,v'
    
    def get_available_symbols(self) -> List[str]:
        """
        Get list of available symbols in SYMBOL-USDT format.
        
        Returns:
            List of symbol names in SYMBOL-USDT format
        """
        if not os.path.exists(self.data_directory):
            logger.error(f"Data directory not found: {self.data_directory}")
            return []
            
        symbols = []
        for item in os.listdir(self.data_directory):
            item_path = os.path.join(self.data_directory, item)
            if os.path.isdir(item_path):
                # Check if price.csv exists in the directory
                price_file = os.path.join(item_path, "price.csv")
                if os.path.exists(price_file) and self.validate_file_format(price_file):
                    # Return symbols in SYMBOL-USDT format for Jesse compatibility
                    symbols.append(f"{item}-USDT")
                    
        return sorted(symbols)
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get information about a specific symbol.
        
        Args:
            symbol: Symbol name (e.g., 'ACH' or 'ACH-USDT')
            
        Returns:
            Dictionary with symbol information or None if not found
        """
        # Normalize symbol
        csv_symbol = self.normalize_symbol(symbol)
        
        # Check cache first
        cache_key = f"symbol_info_{csv_symbol}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        file_path = self.get_file_path(csv_symbol)
        
        if not os.path.exists(file_path):
            logger.error(f"Price file not found for symbol {symbol}: {file_path}")
            return None
            
        try:
            # Read first and last lines to get time range
            with open(file_path, 'r') as f:
                # Skip header
                f.readline()
                
                # Read first data line
                first_line = f.readline().strip()
                if not first_line:
                    logger.error(f"Empty file: {file_path}")
                    return None
                
                # Read last line
                last_line = None
                for line in f:
                    line = line.strip()
                    if line:
                        last_line = line
            
            if not last_line:
                last_line = first_line
            
            # Parse timestamps
            first_timestamp = int(first_line.split(',')[0])
            last_timestamp = int(last_line.split(',')[0])
            
            symbol_info = {
                'symbol': csv_symbol,
                'start_time': first_timestamp,
                'end_time': last_timestamp,
                'file_path': file_path,
                'format': 'kucoin'
            }
            
            # Cache the result
            self.cache[cache_key] = symbol_info
            
            return symbol_info
            
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None
    
    def load_tick_data(self, symbol: str, start_date: Optional[int] = None, 
                      finish_date: Optional[int] = None) -> Optional[pd.DataFrame]:
        """
        Load tick data for a symbol.
        
        Args:
            symbol: Symbol name (e.g., 'ACH' or 'ACH-USDT')
            start_date: Start timestamp in milliseconds (optional)
            finish_date: Finish timestamp in milliseconds (optional)
            
        Returns:
            DataFrame with tick data or None if failed
        """
        # Normalize symbol
        csv_symbol = self.normalize_symbol(symbol)
        
        # Check cache first
        cache_key = f"tick_data_{csv_symbol}_{start_date}_{finish_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        file_path = self.get_file_path(csv_symbol)
        
        if not os.path.exists(file_path):
            logger.error(f"Price file not found for symbol {symbol}: {file_path}")
            return None
            
        try:
            # Read CSV file (skip header row)
            df = pd.read_csv(file_path, names=self.expected_columns, skiprows=1)
            
            # Filter by date range if specified
            if start_date is not None:
                df = df[df['t'] >= start_date]
            if finish_date is not None:
                df = df[df['t'] <= finish_date]
            
            # Sort by timestamp
            df = df.sort_values('t').reset_index(drop=True)
            
            logger.info(f"Loaded {len(df)} ticks for {symbol}")
            
            # Cache the result
            self.cache[cache_key] = df
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading tick data for {symbol}: {e}")
            return None
    
    def aggregate_to_candles(self, tick_data: pd.DataFrame, timeframe: str = "1m") -> np.ndarray:
        """
        Aggregate tick data into OHLCV candles.
        
        Args:
            tick_data: DataFrame with tick data
            timeframe: Target timeframe (e.g., '1m', '5m', '1h')
            
        Returns:
            Numpy array with candles in format [timestamp, open, high, low, close, volume]
        """
        if tick_data.empty:
            return np.array([])
        
        # Convert timeframe to milliseconds
        timeframe_ms = self._timeframe_to_ms(timeframe)
        
        # Create timestamp groups
        tick_data['group'] = (tick_data['t'] // timeframe_ms) * timeframe_ms
        
        # Aggregate by group - fix the column structure
        agg_dict = {
            't': 'first',  # Use first timestamp in group
            'p': ['first', 'max', 'min', 'last'],  # OHLC
            'v': 'sum'  # Volume
        }
        
        candles = tick_data.groupby('group').agg(agg_dict)
        
        # Flatten multi-level columns properly
        candles.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        # Reset index to make group column a regular column
        candles = candles.reset_index(drop=True)
        
        # Convert to numpy array
        result = candles[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values
        
        return result.astype(np.float64)
    
    def get_candles(self, symbol: str, timeframe: str = "1m",
                   start_date: Optional[int] = None,
                   finish_date: Optional[int] = None) -> Optional[np.ndarray]:
        """
        Get candles for a symbol.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe
            start_date: Start timestamp in milliseconds (optional)
            finish_date: Finish timestamp in milliseconds (optional)
            
        Returns:
            Numpy array of candles or None if failed
        """
        # Check cache first
        cache_key = f"candles_{symbol}_{timeframe}_{start_date}_{finish_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Load tick data
        tick_data = self.load_tick_data(symbol, start_date, finish_date)
        if tick_data is None or tick_data.empty:
            # Provide more context about why no data was found
            try:
                symbol_info = self.get_symbol_info(symbol)
                if symbol_info:
                    data_start = symbol_info.get('start_time', 0)
                    data_end = symbol_info.get('end_time', 0)
                    logger.warning(
                        f"No tick data found for {symbol} in timeframe {timeframe}. "
                        f"Available data range: {data_start} - {data_end}, "
                        f"Requested range: {start_date} - {finish_date}"
                    )
            except:
                pass
            return None
        
        # Aggregate to candles
        candles = self.aggregate_to_candles(tick_data, timeframe)
        
        # Cache the result
        self.cache[cache_key] = candles
        
        return candles
    
    def get_file_path(self, symbol: str) -> str:
        """
        Get the file path for a symbol.
        
        Args:
            symbol: Symbol name (without suffix)
            
        Returns:
            Full path to the CSV file
        """
        return os.path.join(self.data_directory, symbol, "price.csv")
    
    def validate_file_format(self, file_path: str) -> bool:
        """
        Validate that the CSV file has the expected format.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            True if format is valid, False otherwise
        """
        try:
            # Check if file exists and is readable
            if not os.path.exists(file_path) or not os.access(file_path, os.R_OK):
                return False
            
            # Read first line to check headers
            with open(file_path, 'r') as f:
                first_line = f.readline().strip()
                if first_line != self.expected_headers:
                    logger.warning(f"Unexpected header format in {file_path}: {first_line}")
                    return False
            
            # Try to read a few lines to validate format
            with open(file_path, 'r') as f:
                lines = [f.readline().strip() for _ in range(3)]  # Read header + 2 data lines
                
                for i, line in enumerate(lines[1:], 1):  # Skip header
                    if not line:
                        continue
                    
                    parts = line.split(',')
                    if len(parts) != 3:
                        logger.warning(f"Invalid line format in {file_path} line {i+1}: {line}")
                        return False
                    
                    # Check if first part is a valid timestamp
                    try:
                        timestamp = int(parts[0])
                        if timestamp < 1000000000000:  # Should be milliseconds
                            logger.warning(f"Invalid timestamp format in {file_path} line {i+1}: {timestamp}")
                            return False
                    except ValueError:
                        logger.warning(f"Invalid timestamp in {file_path} line {i+1}: {parts[0]}")
                        return False
                    
                    # Check if price and volume are numeric
                    try:
                        float(parts[1])  # price
                        float(parts[2])  # volume
                    except ValueError:
                        logger.warning(f"Invalid numeric values in {file_path} line {i+1}: {line}")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating file format for {file_path}: {e}")
            return False
    
    def get_parser_info(self) -> Dict:
        """
        Get information about this parser.
        
        Returns:
            Dictionary with parser information
        """
        return {
            'name': 'KucoinCSVParser',
            'version': '1.0.0',
            'description': 'Parser for KucoinData CSV format',
            'expected_format': 't,p,v (timestamp, price, volume)',
            'file_structure': 'SYMBOL/price.csv',
            'supported_timeframes': ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']
        }
