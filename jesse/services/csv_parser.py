"""
CSV Parser service for Jesse trading framework.
Handles parsing of CSV files containing OHLCV data for backtesting and optimization.
"""

import csv
import os
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import jesse.helpers as jh
from jesse.services import logger


class CSVParser:
    """
    Parser for CSV files containing OHLCV data.
    Supports various CSV formats commonly used in trading data.
    """
    
    # Supported column name variations
    TIMESTAMP_COLUMNS = ['timestamp', 'time', 'date', 'datetime', 'ts']
    OPEN_COLUMNS = ['open', 'o', 'Open', 'OPEN']
    HIGH_COLUMNS = ['high', 'h', 'High', 'HIGH']
    LOW_COLUMNS = ['low', 'l', 'Low', 'LOW']
    CLOSE_COLUMNS = ['close', 'c', 'Close', 'CLOSE']
    VOLUME_COLUMNS = ['volume', 'vol', 'v', 'Volume', 'VOLUME']
    
    def __init__(self, file_path: str, exchange: str = "custom", symbol: str = "BTC-USDT", timeframe: str = "1m"):
        """
        Initialize CSV parser.
        
        Args:
            file_path: Path to CSV file
            exchange: Exchange name (default: "custom")
            symbol: Symbol name (default: "BTC-USDT")
            timeframe: Timeframe (default: "1m")
        """
        self.file_path = file_path
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.data = None
        self.column_mapping = {}
        
    def validate_file(self) -> bool:
        """
        Validate that the CSV file exists and is readable.
        
        Returns:
            bool: True if file is valid, False otherwise
        """
        if not os.path.exists(self.file_path):
            logger.error(f"CSV file not found: {self.file_path}")
            return False
            
        if not os.path.isfile(self.file_path):
            logger.error(f"Path is not a file: {self.file_path}")
            return False
            
        return True
    
    def detect_columns(self, sample_rows: int = 5) -> Dict[str, str]:
        """
        Automatically detect column names in CSV file.
        
        Args:
            sample_rows: Number of rows to sample for detection
            
        Returns:
            Dict mapping standard names to actual column names
        """
        if not self.validate_file():
            return {}
            
        try:
            # Read first few rows to detect columns
            df_sample = pd.read_csv(self.file_path, nrows=sample_rows)
            columns = df_sample.columns.str.lower()
            
            mapping = {}
            
            # Find timestamp column
            for col in self.TIMESTAMP_COLUMNS:
                if col in columns:
                    mapping['timestamp'] = col
                    break
            
            # Find OHLCV columns
            for col in self.OPEN_COLUMNS:
                if col in columns:
                    mapping['open'] = col
                    break
                    
            for col in self.HIGH_COLUMNS:
                if col in columns:
                    mapping['high'] = col
                    break
                    
            for col in self.LOW_COLUMNS:
                if col in columns:
                    mapping['low'] = col
                    break
                    
            for col in self.CLOSE_COLUMNS:
                if col in columns:
                    mapping['close'] = col
                    break
                    
            for col in self.VOLUME_COLUMNS:
                if col in columns:
                    mapping['volume'] = col
                    break
            
            self.column_mapping = mapping
            return mapping
            
        except Exception as e:
            logger.error(f"Error detecting columns: {e}")
            return {}
    
    def parse_csv(self, 
                  timestamp_format: str = "auto",
                  custom_columns: Optional[Dict[str, str]] = None) -> bool:
        """
        Parse CSV file and convert to Jesse format.
        
        Args:
            timestamp_format: Format of timestamp column ("auto", "unix", "iso", "custom")
            custom_columns: Custom column mapping if auto-detection fails
            
        Returns:
            bool: True if parsing successful, False otherwise
        """
        if not self.validate_file():
            return False
            
        try:
            # Use custom columns if provided, otherwise auto-detect
            if custom_columns:
                self.column_mapping = custom_columns
            else:
                self.detect_columns()
            
            # Validate required columns
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in self.column_mapping]
            
            if missing_columns:
                logger.error(f"Missing required columns: {missing_columns}")
                return False
            
            # Read CSV file
            df = pd.read_csv(self.file_path)
            
            # Rename columns to standard names
            df_renamed = df.rename(columns={
                self.column_mapping['timestamp']: 'timestamp',
                self.column_mapping['open']: 'open',
                self.column_mapping['high']: 'high',
                self.column_mapping['low']: 'low',
                self.column_mapping['close']: 'close',
                self.column_mapping['volume']: 'volume'
            })
            
            # Convert timestamp to milliseconds
            df_renamed['timestamp'] = self._convert_timestamp(df_renamed['timestamp'], timestamp_format)
            
            # Sort by timestamp
            df_renamed = df_renamed.sort_values('timestamp').reset_index(drop=True)
            
            # Convert to numpy array in Jesse format: [timestamp, open, close, high, low, volume]
            self.data = df_renamed[['timestamp', 'open', 'close', 'high', 'low', 'volume']].values
            
            logger.info(f"Successfully parsed {len(self.data)} candles from {self.file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error parsing CSV file: {e}")
            return False
    
    def _convert_timestamp(self, timestamps: pd.Series, format_type: str) -> pd.Series:
        """
        Convert timestamp column to milliseconds since epoch.
        
        Args:
            timestamps: Series of timestamp values
            format_type: Format type ("auto", "unix", "iso", "custom")
            
        Returns:
            Series of timestamps in milliseconds
        """
        try:
            if format_type == "auto":
                # Try to auto-detect format
                sample = timestamps.iloc[0]
                
                # Check if it's already a Unix timestamp
                if isinstance(sample, (int, float)) and len(str(int(sample))) >= 10:
                    # Convert to milliseconds if needed
                    if sample < 1e12:  # Unix timestamp in seconds
                        return timestamps * 1000
                    else:  # Already in milliseconds
                        return timestamps
                
                # Try parsing as ISO format
                try:
                    pd.to_datetime(timestamps)
                    return pd.to_datetime(timestamps).astype(np.int64) // 10**6
                except:
                    pass
                
                # Try parsing as common date formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']:
                    try:
                        return pd.to_datetime(timestamps, format=fmt).astype(np.int64) // 10**6
                    except:
                        continue
                        
                raise ValueError("Could not auto-detect timestamp format")
                
            elif format_type == "unix":
                # Unix timestamp in seconds
                return timestamps * 1000
                
            elif format_type == "iso":
                # ISO format
                return pd.to_datetime(timestamps).astype(np.int64) // 10**6
                
            else:
                # Custom format
                return pd.to_datetime(timestamps, format=format_type).astype(np.int64) // 10**6
                
        except Exception as e:
            logger.error(f"Error converting timestamps: {e}")
            raise
    
    def get_candles(self) -> Optional[np.ndarray]:
        """
        Get parsed candles data.
        
        Returns:
            numpy array of candles in Jesse format or None if not parsed
        """
        return self.data
    
    def get_candles_info(self) -> Dict:
        """
        Get information about parsed candles.
        
        Returns:
            Dictionary with candles information
        """
        if self.data is None:
            return {}
            
        return {
            'count': len(self.data),
            'start_time': self.data[0][0] if len(self.data) > 0 else None,
            'end_time': self.data[-1][0] if len(self.data) > 0 else None,
            'exchange': self.exchange,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'file_path': self.file_path
        }
    
    def save_to_database(self) -> bool:
        """
        Save parsed candles to Jesse database.
        
        Returns:
            bool: True if saved successfully, False otherwise
        """
        if self.data is None:
            logger.error("No data to save. Parse CSV first.")
            return False
            
        try:
            from jesse.services.db import database
            from jesse.models.Candle import Candle
            
            database.open_connection()
            
            # Clear existing data for this exchange/symbol/timeframe
            Candle.delete().where(
                (Candle.exchange == self.exchange) &
                (Candle.symbol == self.symbol) &
                (Candle.timeframe == self.timeframe)
            ).execute()
            
            # Insert new data
            candles_to_insert = []
            for candle in self.data:
                candles_to_insert.append({
                    'id': jh.generate_unique_id(),
                    'timestamp': int(candle[0]),
                    'open': float(candle[1]),
                    'close': float(candle[2]),
                    'high': float(candle[3]),
                    'low': float(candle[4]),
                    'volume': float(candle[5]),
                    'exchange': self.exchange,
                    'symbol': self.symbol,
                    'timeframe': self.timeframe
                })
            
            # Batch insert
            Candle.insert_many(candles_to_insert).execute()
            
            database.close_connection()
            logger.info(f"Successfully saved {len(candles_to_insert)} candles to database")
            return True
            
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            return False


def parse_csv_file(file_path: str, 
                  exchange: str = "custom", 
                  symbol: str = "BTC-USDT", 
                  timeframe: str = "1m",
                  timestamp_format: str = "auto",
                  custom_columns: Optional[Dict[str, str]] = None) -> Optional[CSVParser]:
    """
    Convenience function to parse a CSV file.
    
    Args:
        file_path: Path to CSV file
        exchange: Exchange name
        symbol: Symbol name
        timeframe: Timeframe
        timestamp_format: Timestamp format
        custom_columns: Custom column mapping
        
    Returns:
        CSVParser instance if successful, None otherwise
    """
    parser = CSVParser(file_path, exchange, symbol, timeframe)
    
    if parser.parse_csv(timestamp_format, custom_columns):
        return parser
    else:
        return None


def get_csv_candles(file_path: str,
                   exchange: str = "custom",
                   symbol: str = "BTC-USDT", 
                   timeframe: str = "1m",
                   start_date: Optional[int] = None,
                   finish_date: Optional[int] = None) -> Optional[np.ndarray]:
    """
    Get candles from CSV file with optional date filtering.
    
    Args:
        file_path: Path to CSV file
        exchange: Exchange name
        symbol: Symbol name
        timeframe: Timeframe
        start_date: Start timestamp in milliseconds (optional)
        finish_date: Finish timestamp in milliseconds (optional)
        
    Returns:
        numpy array of candles or None if failed
    """
    parser = CSVParser(file_path, exchange, symbol, timeframe)
    
    if not parser.parse_csv():
        return None
    
    candles = parser.get_candles()
    
    if candles is None:
        return None
    
    # Apply date filtering if specified
    if start_date is not None:
        candles = candles[candles[:, 0] >= start_date]
    
    if finish_date is not None:
        candles = candles[candles[:, 0] <= finish_date]
    
    return candles
