"""
Base CSV Parser interface for CustomCSV driver.

This module defines the abstract interface that all CSV parsers must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
import os


class BaseCSVParser(ABC):
    """
    Abstract base class for CSV parsers.
    
    All CSV parsers must implement this interface to be compatible with CustomCSV driver.
    """
    
    def __init__(self, data_directory: str):
        """
        Initialize CSV parser.
        
        Args:
            data_directory: Base directory containing CSV data files
        """
        self.data_directory = data_directory
        self.cache = {}  # Cache for loaded data
        
    @abstractmethod
    def get_available_symbols(self) -> List[str]:
        """
        Get list of available symbols.
        
        Returns:
            List of symbol names in SYMBOL-USDT format
        """
        pass
    
    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get information about a specific symbol.
        
        Args:
            symbol: Symbol name (e.g., 'ACH' or 'ACH-USDT')
            
        Returns:
            Dictionary with symbol information or None if not found
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def aggregate_to_candles(self, tick_data: pd.DataFrame, timeframe: str = "1m") -> np.ndarray:
        """
        Aggregate tick data into OHLCV candles.
        
        Args:
            tick_data: DataFrame with tick data
            timeframe: Target timeframe (e.g., '1m', '5m', '1h')
            
        Returns:
            Numpy array with candles in format [timestamp, open, high, low, close, volume]
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def get_file_path(self, symbol: str) -> str:
        """
        Get the file path for a symbol.
        
        Args:
            symbol: Symbol name (without suffix)
            
        Returns:
            Full path to the CSV file
        """
        pass
    
    @abstractmethod
    def validate_file_format(self, file_path: str) -> bool:
        """
        Validate that the CSV file has the expected format.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            True if format is valid, False otherwise
        """
        pass
    
    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol by removing common suffixes.
        
        Args:
            symbol: Trading symbol (e.g., 'ACH-USDT')
            
        Returns:
            Normalized symbol for file lookup (e.g., 'ACH')
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
    
    def symbol_exists(self, symbol: str) -> bool:
        """
        Check if symbol exists in data directory.
        
        Args:
            symbol: Symbol name (without suffix)
            
        Returns:
            True if symbol exists, False otherwise
        """
        file_path = self.get_file_path(symbol)
        return os.path.exists(file_path) and self.validate_file_format(file_path)
    
    def clear_cache(self):
        """
        Clear all caches.
        """
        self.cache.clear()
    
    def get_data_directory(self) -> str:
        """
        Get the current data directory path.
        
        Returns:
            Path to data directory
        """
        return self.data_directory
    
    def set_data_directory(self, data_directory: str):
        """
        Set a new data directory.
        
        Args:
            data_directory: New path to data directory
        """
        if not os.path.exists(data_directory):
            raise FileNotFoundError(f"Data directory not found: {data_directory}")
        
        self.data_directory = data_directory
        self.clear_cache()
    
    def _timeframe_to_ms(self, timeframe: str) -> int:
        """
        Convert timeframe string to milliseconds.
        
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

