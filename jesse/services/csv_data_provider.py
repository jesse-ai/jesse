"""
CSV Data Provider for Jesse trading framework.
Handles loading and aggregating tick data from CSV files into OHLCV candles.
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import jesse.helpers as jh
from jesse.services import logger
from jesse.services.csv_parser import CSVParser


class CSVDataProvider:
    """
    Data provider for CSV files containing tick data.
    Aggregates tick data into OHLCV candles for backtesting.
    """
    
    def __init__(self, data_directory: str = "/Users/alxy/Downloads/Fond/KucoinData"):
        """
        Initialize CSV data provider.
        
        Args:
            data_directory: Base directory containing CSV data files
        """
        self.data_directory = data_directory
        self.cache = {}  # Cache for loaded data
        
    def get_available_symbols(self) -> List[str]:
        """
        Get list of available symbols in SYMBOL-USDT format.
        
        Returns:
            List of symbol names in SYMBOL-USDT format
        """
        if not os.path.exists(self.data_directory):
            return []
            
        symbols = []
        for item in os.listdir(self.data_directory):
            item_path = os.path.join(self.data_directory, item)
            if os.path.isdir(item_path):
                # Check if price.csv exists in the directory
                price_file = os.path.join(item_path, "price.csv")
                if os.path.exists(price_file):
                    # Return symbols in SYMBOL-USDT format for Jesse compatibility
                    symbols.append(f"{item}-USDT")
                    
        return sorted(symbols)
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get information about a symbol's data.
        
        Args:
            symbol: Symbol name (e.g., 'ACH' or 'ACH-USDT')
            
        Returns:
            Dictionary with symbol information or None if not found
        """
        # Remove common suffixes from symbol for file lookup
        csv_symbol = symbol
        if symbol.endswith('-USDT'):
            csv_symbol = symbol.replace('-USDT', '')
        elif symbol.endswith('-USDC'):
            csv_symbol = symbol.replace('-USDC', '')
        elif symbol.endswith('-BTC'):
            csv_symbol = symbol.replace('-BTC', '')
        elif symbol.endswith('-ETH'):
            csv_symbol = symbol.replace('-ETH', '')
        
        price_file = os.path.join(self.data_directory, csv_symbol, "price.csv")
        
        if not os.path.exists(price_file):
            return None
            
        try:
            # Read first and last lines to get time range
            with open(price_file, 'r') as f:
                first_line = f.readline().strip()  # Skip header
                first_line = f.readline().strip()  # Get first data line
                f.seek(0, 2)  # Go to end of file
                file_size = f.tell()
                
                # Read last line
                f.seek(max(0, file_size - 1000))  # Read last 1000 bytes
                last_chunk = f.read()
                last_line = last_chunk.split('\n')[-2] if '\n' in last_chunk else last_chunk
            
            # Parse first and last timestamps
            first_parts = first_line.split(',')
            last_parts = last_line.split(',')
            
            if len(first_parts) >= 1 and len(last_parts) >= 1:
                start_time = int(first_parts[0])  # timestamp is in first column
                end_time = int(last_parts[0])
                
                return {
                    'symbol': symbol,
                    'start_time': start_time,
                    'end_time': end_time,
                    'start_date': jh.timestamp_to_date(start_time),
                    'end_date': jh.timestamp_to_date(end_time),
                    'file_path': price_file,
                    'file_size': file_size
                }
                
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
        # Remove common suffixes from symbol for file lookup
        csv_symbol = symbol
        if symbol.endswith('-USDT'):
            csv_symbol = symbol.replace('-USDT', '')
        elif symbol.endswith('-USDC'):
            csv_symbol = symbol.replace('-USDC', '')
        elif symbol.endswith('-BTC'):
            csv_symbol = symbol.replace('-BTC', '')
        elif symbol.endswith('-ETH'):
            csv_symbol = symbol.replace('-ETH', '')
        
        price_file = os.path.join(self.data_directory, csv_symbol, "price.csv")
        
        if not os.path.exists(price_file):
            logger.error(f"Price file not found for symbol {symbol}: {price_file}")
            return None
            
        try:
            # Read CSV file (skip header row)
            df = pd.read_csv(price_file, names=['timestamp', 'price', 'volume'], skiprows=1)
            
            # Filter by date range if specified
            if start_date is not None:
                df = df[df['timestamp'] >= start_date]
            if finish_date is not None:
                df = df[df['timestamp'] <= finish_date]
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            logger.info(f"Loaded {len(df)} ticks for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error loading tick data for {symbol}: {e}")
            return None
    
    def aggregate_to_candles(self, tick_data: pd.DataFrame, timeframe: str = "1m") -> np.ndarray:
        """
        Aggregate tick data into OHLCV candles.
        
        Args:
            tick_data: DataFrame with tick data
            timeframe: Target timeframe (e.g., "1m", "5m", "1h")
            
        Returns:
            numpy array of candles in Jesse format
        """
        if tick_data is None or len(tick_data) == 0:
            return np.array([])
            
        try:
            # Convert timeframe to minutes
            timeframe_minutes = jh.timeframe_to_one_minutes(timeframe)
            timeframe_ms = timeframe_minutes * 60 * 1000  # Convert to milliseconds
            
            # Group ticks by timeframe
            tick_data['candle_timestamp'] = (tick_data['timestamp'] // timeframe_ms) * timeframe_ms
            
            # Aggregate to OHLCV
            candles = tick_data.groupby('candle_timestamp').agg({
                'price': ['first', 'last', 'max', 'min'],  # OHLC
                'volume': 'sum'  # Volume
            }).reset_index()
            
            # Flatten column names
            candles.columns = ['timestamp', 'open', 'close', 'high', 'low', 'volume']
            
            # Convert to numpy array in Jesse format: [timestamp, open, close, high, low, volume]
            result = candles[['timestamp', 'open', 'close', 'high', 'low', 'volume']].values
            
            logger.info(f"Aggregated {len(tick_data)} ticks into {len(result)} {timeframe} candles")
            return result
            
        except Exception as e:
            logger.error(f"Error aggregating tick data to candles: {e}")
            return np.array([])
    
    def get_candles(self, symbol: str, timeframe: str = "1m", 
                   start_date: Optional[int] = None, 
                   finish_date: Optional[int] = None) -> Optional[np.ndarray]:
        """
        Get candles for a symbol and timeframe.
        
        Args:
            symbol: Symbol name (e.g., 'ACH' or 'ACH-USDT')
            timeframe: Timeframe
            start_date: Start timestamp in milliseconds (optional)
            finish_date: Finish timestamp in milliseconds (optional)
            
        Returns:
            numpy array of candles or None if failed
        """
        # Create cache key
        cache_key = f"{symbol}_{timeframe}_{start_date}_{finish_date}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Load tick data
        tick_data = self.load_tick_data(symbol, start_date, finish_date)
        
        if tick_data is None:
            return None
        
        # Aggregate to candles
        candles = self.aggregate_to_candles(tick_data, timeframe)
        
        # Cache result
        self.cache[cache_key] = candles
        
        return candles
    
    def save_candles_to_database(self, symbol: str, timeframe: str = "1m",
                               exchange: str = "custom", 
                               start_date: Optional[int] = None,
                               finish_date: Optional[int] = None) -> bool:
        """
        Save candles to Jesse database.
        
        Args:
            symbol: Symbol name (e.g., 'ACH' or 'ACH-USDT')
            timeframe: Timeframe
            exchange: Exchange name
            start_date: Start timestamp in milliseconds (optional)
            finish_date: Finish timestamp in milliseconds (optional)
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        candles = self.get_candles(symbol, timeframe, start_date, finish_date)
        
        if candles is None or len(candles) == 0:
            logger.error(f"No candles to save for {symbol}")
            return False
        
        try:
            from jesse.services.db import database
            from jesse.models.Candle import Candle
            import os
            
            # Ensure we're in a Jesse project directory
            if not jh.is_jesse_project():
                # Try to find Jesse project directory
                current_dir = os.getcwd()
                if 'project-template' in current_dir:
                    # We're already in the right place
                    pass
                else:
                    # Try to change to project-template directory
                    project_template_dir = '/Users/alxy/Desktop/1PROJ/JesseLocal/project-template'
                    if os.path.exists(project_template_dir):
                        os.chdir(project_template_dir)
            
            database.open_connection()
            
            # Clear existing data for this exchange/symbol/timeframe
            Candle.delete().where(
                (Candle.exchange == 'custom') &
                (Candle.symbol == symbol) &
                (Candle.timeframe == timeframe)
            ).execute()
            
            # Insert new data in batches to avoid connection timeout
            batch_size = 1000  # Insert 1000 candles at a time
            total_candles = len(candles)
            
            for i in range(0, total_candles, batch_size):
                batch_candles = candles[i:i + batch_size]
                candles_to_insert = []
                
                for candle in batch_candles:
                    candles_to_insert.append({
                        'id': jh.generate_unique_id(),
                        'timestamp': int(candle[0]),
                        'open': float(candle[1]),
                        'close': float(candle[2]),
                        'high': float(candle[3]),
                        'low': float(candle[4]),
                        'volume': float(candle[5]),
                        'exchange': 'custom',
                        'symbol': symbol,
                        'timeframe': timeframe
                    })
                
                # Insert batch
                Candle.insert_many(candles_to_insert).execute()
                print(f"   📊 Вставлено {min(i + batch_size, total_candles)} из {total_candles} свечей")
            
            database.close_connection()
            logger.info(f"Successfully saved {len(candles_to_insert)} candles to database")
            return True
            
        except Exception as e:
            print(f"❌ Error saving candles to database: {e}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
            logger.error(f"Error saving candles to database: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def get_available_timeframes(self, symbol: str) -> List[str]:
        """
        Get available timeframes for a symbol based on data frequency.
        
        Args:
            symbol: Symbol name
            
        Returns:
            List of available timeframes
        """
        # For tick data, we can generate any timeframe
        return ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]
    
    def clear_cache(self):
        """Clear the data cache."""
        self.cache.clear()
        logger.info("CSV data cache cleared")


# Global instance
csv_data_provider = CSVDataProvider(data_directory="/Users/alxy/Downloads/Fond/KucoinData")


def get_csv_candles(symbol: str, timeframe: str = "1m",
                   start_date: Optional[int] = None,
                   finish_date: Optional[int] = None) -> Optional[np.ndarray]:
    """
    Convenience function to get candles from CSV data.
    
    Args:
        symbol: Symbol name
        timeframe: Timeframe
        start_date: Start timestamp in milliseconds (optional)
        finish_date: Finish timestamp in milliseconds (optional)
        
    Returns:
        numpy array of candles or None if failed
    """
    return csv_data_provider.get_candles(symbol, timeframe, start_date, finish_date)


def get_available_csv_symbols() -> List[str]:
    """
    Get list of available symbols from CSV data.
    
    Returns:
        List of symbol names
    """
    return csv_data_provider.get_available_symbols()


def import_csv_symbol_to_database(symbol: str, timeframe: str = "1m",
                                exchange: str = "custom",
                                start_date: Optional[int] = None,
                                finish_date: Optional[int] = None) -> bool:
    """
    Import a CSV symbol to Jesse database.
    
    Args:
        symbol: Symbol name
        timeframe: Timeframe
        exchange: Exchange name
        start_date: Start timestamp in milliseconds (optional)
        finish_date: Finish timestamp in milliseconds (optional)
        
    Returns:
        bool: True if imported successfully, False otherwise
    """
    return csv_data_provider.save_candles_to_database(
        symbol, timeframe, exchange, start_date, finish_date
    )
