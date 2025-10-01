"""
Batch CSV Loader for CustomCSV driver.

This module provides functionality for batch loading all symbols from a directory
with detailed progress reporting and statistics.
"""

import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import jesse.helpers as jh
from jesse.services import logger

from .CustomCSV import CustomCSV
from .csv_parsers import CSVParserFactory

# Database imports
try:
    from jesse.services.db import database
    from jesse.models.Candle import Candle, store_candles_into_db
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    logger.warning("Database modules not available. Database saving will be disabled.")


@dataclass
class SymbolLoadResult:
    """Result of loading a single symbol"""
    symbol: str
    success: bool
    candles_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    load_duration: float = 0.0
    saved_to_db: bool = False
    db_save_duration: float = 0.0
    db_error_message: Optional[str] = None
    timeframe: str = "1m"


@dataclass
class BatchLoadReport:
    """Report of batch loading operation"""
    total_symbols: int
    successful_loads: int
    failed_loads: int
    total_candles: int
    total_duration: float
    start_time: datetime
    end_time: datetime
    results: List[SymbolLoadResult]
    errors: List[str]
    saved_to_db: int = 0
    db_save_failures: int = 0
    total_db_save_duration: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_symbols == 0:
            return 0.0
        return (self.successful_loads / self.total_symbols) * 100
    
    @property
    def db_save_rate(self) -> float:
        """Calculate database save rate percentage"""
        if self.successful_loads == 0:
            return 0.0
        return (self.saved_to_db / self.successful_loads) * 100
    
    @property
    def average_candles_per_symbol(self) -> float:
        """Calculate average candles per successful symbol"""
        if self.successful_loads == 0:
            return 0.0
        return self.total_candles / self.successful_loads


class BatchCSVLoader:
    """
    Batch loader for CSV data from directory.
    
    Provides functionality to load all available symbols from a directory
    with progress reporting and detailed statistics.
    """
    
    def __init__(self, data_directory: Optional[str] = None, parser_type: Optional[str] = None):
        """
        Initialize batch CSV loader.
        
        Args:
            data_directory: Path to directory containing CSV data files
            parser_type: Specific CSV parser type to use
        """
        self.data_directory = data_directory or os.getenv('CSV_DATA_DIR', "/Users/alxy/Downloads/Fond/KucoinData")
        self.parser_type = parser_type
        
        # Initialize CSV driver with unlimited candles
        self.csv_driver = CustomCSV(data_directory=self.data_directory, parser_type=parser_type, max_candles=0)
        
        # Statistics
        self.stats = {
            'total_symbols': 0,
            'successful_loads': 0,
            'failed_loads': 0,
            'total_candles': 0,
            'start_time': None,
            'end_time': None
        }
    
    def get_available_symbols(self) -> List[str]:
        """
        Get list of available symbols in the directory.
        
        Returns:
            List of available symbols
        """
        return self.csv_driver.get_available_symbols()
    
    def load_single_symbol(self, symbol: str, timeframe: str = "1m", 
                          max_candles: int = 1000) -> SymbolLoadResult:
        """
        Load data for a single symbol.
        
        Args:
            symbol: Symbol to load
            timeframe: Timeframe for candles
            max_candles: Maximum number of candles to load
            
        Returns:
            SymbolLoadResult with loading details
        """
        start_time = time.time()
        result = SymbolLoadResult(
            symbol=symbol,
            success=False,
            timeframe=timeframe
        )
        
        try:
            # Get symbol info
            symbol_info = self.csv_driver.get_exchange_info(symbol)
            if symbol_info:
                # Convert timestamps to datetime objects
                from datetime import datetime
                result.start_time = datetime.fromtimestamp(symbol_info['start_time'] / 1000)
                result.end_time = datetime.fromtimestamp(symbol_info['end_time'] / 1000)
            
            # Load candles
            start_timestamp = symbol_info['start_time'] if symbol_info else int(time.time() * 1000)
            candles = self.csv_driver.fetch(symbol, start_timestamp, timeframe)
            
            result.success = True
            result.candles_count = len(candles)
            
        except Exception as e:
            result.error_message = str(e)
            logger.error(f"Failed to load {symbol}: {e}")
        
        result.load_duration = time.time() - start_time
        return result
    
    def load_all_symbols(self, timeframe: str = "1m", max_candles: int = 1000,
                        max_workers: int = 4, progress_callback: Optional[callable] = None) -> BatchLoadReport:
        """
        Load all available symbols from directory.
        
        Args:
            timeframe: Timeframe for candles
            max_candles: Maximum number of candles per symbol
            max_workers: Maximum number of concurrent workers
            progress_callback: Optional callback for progress updates
            
        Returns:
            BatchLoadReport with detailed results
        """
        logger.info("Starting batch CSV loading...")
        
        # Get available symbols
        symbols = self.get_available_symbols()
        total_symbols = len(symbols)
        
        if total_symbols == 0:
            logger.warning("No symbols found in directory")
            return BatchLoadReport(
                total_symbols=0,
                successful_loads=0,
                failed_loads=0,
                total_candles=0,
                total_duration=0.0,
                start_time=datetime.now(),
                end_time=datetime.now(),
                results=[],
                errors=[]
            )
        
        logger.info(f"Found {total_symbols} symbols to load")
        
        # Initialize statistics
        self.stats = {
            'total_symbols': total_symbols,
            'successful_loads': 0,
            'failed_loads': 0,
            'total_candles': 0,
            'start_time': datetime.now(),
            'end_time': None
        }
        
        results = []
        errors = []
        
        # Load symbols
        if max_workers == 1:
            # Sequential loading
            for i, symbol in enumerate(symbols):
                logger.info(f"Loading {symbol} ({i+1}/{total_symbols})")
                result = self.load_single_symbol(symbol, timeframe, max_candles)
                results.append(result)
                
                # Update statistics
                if result.success:
                    self.stats['successful_loads'] += 1
                    self.stats['total_candles'] += result.candles_count
                else:
                    self.stats['failed_loads'] += 1
                    if result.error_message:
                        errors.append(f"{symbol}: {result.error_message}")
                
                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_symbols, result)
        else:
            # Parallel loading
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_symbol = {
                    executor.submit(self.load_single_symbol, symbol, timeframe, max_candles): symbol
                    for symbol in symbols
                }
                
                # Process completed tasks
                completed = 0
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    completed += 1
                    
                    try:
                        result = future.result()
                        results.append(result)
                        
                        # Update statistics
                        if result.success:
                            self.stats['successful_loads'] += 1
                            self.stats['total_candles'] += result.candles_count
                        else:
                            self.stats['failed_loads'] += 1
                            if result.error_message:
                                errors.append(f"{symbol}: {result.error_message}")
                        
                        logger.info(f"Completed {symbol} ({completed}/{total_symbols})")
                        
                        # Progress callback
                        if progress_callback:
                            progress_callback(completed, total_symbols, result)
                            
                    except Exception as e:
                        logger.error(f"Error processing {symbol}: {e}")
                        self.stats['failed_loads'] += 1
                        errors.append(f"{symbol}: {e}")
        
        # Finalize statistics
        self.stats['end_time'] = datetime.now()
        total_duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        # Create report
        report = BatchLoadReport(
            total_symbols=total_symbols,
            successful_loads=self.stats['successful_loads'],
            failed_loads=self.stats['failed_loads'],
            total_candles=self.stats['total_candles'],
            total_duration=total_duration,
            start_time=self.stats['start_time'],
            end_time=self.stats['end_time'],
            results=results,
            errors=errors
        )
        
        logger.info(f"Batch loading completed: {report.success_rate:.1f}% success rate")
        return report
    
    def load_symbols_by_pattern(self, pattern: str, timeframe: str = "1m", 
                               max_candles: int = 1000) -> BatchLoadReport:
        """
        Load symbols matching a specific pattern.
        
        Args:
            pattern: Pattern to match symbol names (case-insensitive)
            timeframe: Timeframe for candles
            max_candles: Maximum number of candles per symbol
            
        Returns:
            BatchLoadReport with detailed results
        """
        all_symbols = self.get_available_symbols()
        matching_symbols = [s for s in all_symbols if pattern.lower() in s.lower()]
        
        logger.info(f"Found {len(matching_symbols)} symbols matching pattern '{pattern}'")
        
        # Temporarily replace the driver's symbol list
        original_symbols = self.csv_driver.get_available_symbols()
        self.csv_driver._available_symbols_cache = matching_symbols
        
        try:
            report = self.load_all_symbols(timeframe, max_candles, max_workers=1)
        finally:
            # Restore original symbol list
            self.csv_driver._available_symbols_cache = original_symbols
        
        return report
    
    def generate_report(self, report: BatchLoadReport, save_to_file: Optional[str] = None) -> str:
        """
        Generate a detailed text report from batch loading results.
        
        Args:
            report: BatchLoadReport to generate report from
            save_to_file: Optional file path to save report
            
        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=" * 80)
        lines.append("BATCH CSV LOADING REPORT")
        lines.append("=" * 80)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Data Directory: {self.data_directory}")
        lines.append(f"Parser Type: {self.parser_type or 'Auto-detected'}")
        lines.append("")
        
        # Summary statistics
        lines.append("SUMMARY STATISTICS")
        lines.append("-" * 40)
        lines.append(f"Total Symbols: {report.total_symbols}")
        lines.append(f"Successful Loads: {report.successful_loads}")
        lines.append(f"Failed Loads: {report.failed_loads}")
        lines.append(f"Success Rate: {report.success_rate:.1f}%")
        lines.append(f"Total Candles: {report.total_candles:,}")
        lines.append(f"Average Candles per Symbol: {report.average_candles_per_symbol:.1f}")
        lines.append(f"Total Duration: {report.total_duration:.2f} seconds")
        lines.append(f"Average Time per Symbol: {report.total_duration / report.total_symbols:.2f} seconds")
        
        # Database save statistics
        if hasattr(report, 'saved_to_db') and report.saved_to_db > 0:
            lines.append("")
            lines.append("DATABASE SAVE STATISTICS")
            lines.append("-" * 40)
            lines.append(f"Saved to Database: {report.saved_to_db}")
            lines.append(f"Database Save Failures: {report.db_save_failures}")
            lines.append(f"Database Save Rate: {report.db_save_rate:.1f}%")
            if report.total_db_save_duration > 0:
                lines.append(f"Total DB Save Duration: {report.total_db_save_duration:.2f} seconds")
                lines.append(f"Average DB Save Time: {report.total_db_save_duration / report.saved_to_db:.2f} seconds per symbol")
        
        lines.append("")
        
        # Detailed results
        lines.append("DETAILED RESULTS")
        lines.append("-" * 40)
        for result in report.results:
            status = "✅ SUCCESS" if result.success else "❌ FAILED"
            lines.append(f"{status} {result.symbol}")
            if result.success:
                lines.append(f"    Candles: {result.candles_count:,}")
                lines.append(f"    Duration: {result.load_duration:.2f}s")
                if result.start_time and result.end_time:
                    lines.append(f"    Data Range: {result.start_time} - {result.end_time}")
                
                # Database save information
                if hasattr(result, 'saved_to_db'):
                    if result.saved_to_db:
                        lines.append(f"    Database: ✅ Saved ({result.db_save_duration:.2f}s)")
                    else:
                        lines.append(f"    Database: ❌ Failed - {result.db_error_message}")
            else:
                lines.append(f"    Error: {result.error_message}")
            lines.append("")
        
        # Errors summary
        if report.errors:
            lines.append("ERRORS SUMMARY")
            lines.append("-" * 40)
            for error in report.errors:
                lines.append(f"• {error}")
            lines.append("")
        
        # Performance metrics
        lines.append("PERFORMANCE METRICS")
        lines.append("-" * 40)
        if report.total_candles > 0:
            candles_per_second = report.total_candles / report.total_duration
            lines.append(f"Candles per Second: {candles_per_second:.1f}")
        
        successful_results = [r for r in report.results if r.success]
        if successful_results:
            avg_load_time = sum(r.load_duration for r in successful_results) / len(successful_results)
            lines.append(f"Average Load Time: {avg_load_time:.2f} seconds")
        
        lines.append("=" * 80)
        
        report_text = "\n".join(lines)
        
        # Save to file if requested
        if save_to_file:
            try:
                with open(save_to_file, 'w', encoding='utf-8') as f:
                    f.write(report_text)
                logger.info(f"Report saved to: {save_to_file}")
            except Exception as e:
                logger.error(f"Failed to save report to {save_to_file}: {e}")
        
        return report_text
    
    def get_directory_info(self) -> Dict:
        """
        Get information about the data directory.
        
        Returns:
            Dictionary with directory information
        """
        info = {
            'directory': self.data_directory,
            'exists': os.path.exists(self.data_directory),
            'symbol_count': 0,
            'parser_info': None,
            'symbols': []
        }
        
        if info['exists']:
            try:
                info['symbol_count'] = len(self.get_available_symbols())
                info['symbols'] = self.get_available_symbols()[:10]  # First 10 symbols
                info['parser_info'] = self.csv_driver.get_parser_info()
            except Exception as e:
                info['error'] = str(e)
        
        return info
    
    def save_symbol_to_database(self, symbol: str, timeframe: str = "1m", 
                               exchange: str = "CustomCSV", 
                               max_candles: int = 0) -> SymbolLoadResult:
        """
        Load and save a single symbol to database.
        
        Args:
            symbol: Symbol to load
            timeframe: Timeframe for candles
            exchange: Exchange name for database
            max_candles: Maximum candles to load (0 = unlimited)
            
        Returns:
            SymbolLoadResult with database save information
        """
        result = SymbolLoadResult(symbol=symbol, success=False, timeframe=timeframe)
        
        try:
            # Load data first
            load_start = time.time()
            result = self.load_single_symbol(symbol, timeframe, max_candles)
            load_duration = time.time() - load_start
            result.load_duration = load_duration
            
            if not result.success:
                return result
            
            # Save to database
            if not DATABASE_AVAILABLE:
                result.db_error_message = "Database not available"
                return result
            
            db_start = time.time()
            
            # Get candles data
            symbol_info = self.csv_driver.get_exchange_info(symbol)
            if not symbol_info:
                result.db_error_message = "Could not get symbol info"
                return result
            
            start_timestamp = symbol_info['start_time']
            end_timestamp = symbol_info['end_time']
            
            # Load candles
            candles = self.csv_driver.get_candles(symbol, start_timestamp, end_timestamp)
            if not candles or len(candles) == 0:
                result.db_error_message = f"No candles to save (got {len(candles) if candles else 0} candles)"
                return result
            
            # Convert to numpy array for database storage
            import numpy as np
            
            # Convert list of dicts to numpy array
            if isinstance(candles, list) and len(candles) > 0 and isinstance(candles[0], dict):
                # Convert from Jesse format (list of dicts) to numpy array
                candles_list = []
                for candle in candles:
                    candles_list.append([
                        candle['timestamp'],
                        candle['open'],
                        candle['close'],
                        candle['high'],
                        candle['low'],
                        candle['volume']
                    ])
                candles_array = np.array(candles_list)
            else:
                candles_array = np.array(candles)
            
            # Ensure database connection
            database.open_connection()
            
            # Clear existing data for this exchange/symbol/timeframe
            Candle.delete().where(
                (Candle.exchange == exchange) &
                (Candle.symbol == symbol) &
                (Candle.timeframe == timeframe)
            ).execute()
            
            # Save to database using Jesse's function
            store_candles_into_db(exchange, symbol, timeframe, candles_array, on_conflict='replace')
            
            database.close_connection()
            
            db_duration = time.time() - db_start
            result.saved_to_db = True
            result.db_save_duration = db_duration
            
            logger.info(f"Successfully saved {len(candles)} candles for {symbol} to database in {db_duration:.2f}s")
            
        except Exception as e:
            result.db_error_message = str(e)
            logger.error(f"Error saving {symbol} to database: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        return result
    
    def save_all_symbols_to_database(self, timeframe: str = "1m", 
                                   exchange: str = "CustomCSV",
                                   max_candles: int = 0,
                                   max_workers: int = 1,
                                   progress_callback: Optional[callable] = None) -> BatchLoadReport:
        """
        Load and save all symbols to database.
        
        Args:
            timeframe: Timeframe for candles
            exchange: Exchange name for database
            max_candles: Maximum candles per symbol (0 = unlimited)
            max_workers: Number of parallel workers
            progress_callback: Callback function for progress updates
            
        Returns:
            BatchLoadReport with database save statistics
        """
        if not DATABASE_AVAILABLE:
            raise Exception("Database not available. Cannot save to database.")
        
        logger.info(f"Starting batch save to database for {self.data_directory}")
        logger.info(f"Exchange: {exchange}, Timeframe: {timeframe}, Max candles: {max_candles}")
        
        # Get symbols to process
        symbols = self.get_available_symbols()
        total_symbols = len(symbols)
        
        if total_symbols == 0:
            logger.warning("No symbols found to save")
            return BatchLoadReport(
                total_symbols=0,
                successful_loads=0,
                failed_loads=0,
                total_candles=0,
                total_duration=0.0,
                start_time=datetime.now(),
                end_time=datetime.now(),
                results=[],
                errors=["No symbols found"]
            )
        
        logger.info(f"Found {total_symbols} symbols to save to database")
        
        # Initialize statistics
        self.stats = {
            'total_symbols': total_symbols,
            'successful_loads': 0,
            'failed_loads': 0,
            'total_candles': 0,
            'saved_to_db': 0,
            'db_save_failures': 0,
            'start_time': datetime.now(),
            'end_time': None
        }
        
        results = []
        errors = []
        
        # Save symbols
        if max_workers == 1:
            # Sequential saving
            for i, symbol in enumerate(symbols):
                logger.info(f"Saving {symbol} to database ({i+1}/{total_symbols})")
                result = self.save_symbol_to_database(symbol, timeframe, exchange, max_candles)
                results.append(result)
                
                # Update statistics
                if result.success:
                    self.stats['successful_loads'] += 1
                    self.stats['total_candles'] += result.candles_count
                    if result.saved_to_db:
                        self.stats['saved_to_db'] += 1
                    else:
                        self.stats['db_save_failures'] += 1
                        if result.db_error_message:
                            errors.append(f"{symbol} DB save failed: {result.db_error_message}")
                else:
                    self.stats['failed_loads'] += 1
                    if result.error_message:
                        errors.append(f"{symbol}: {result.error_message}")
                
                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_symbols, result)
        else:
            # Parallel saving
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_symbol = {
                    executor.submit(self.save_symbol_to_database, symbol, timeframe, exchange, max_candles): symbol
                    for symbol in symbols
                }
                
                # Process completed tasks
                completed = 0
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        result = future.result()
                        results.append(result)
                        
                        # Update statistics
                        if result.success:
                            self.stats['successful_loads'] += 1
                            self.stats['total_candles'] += result.candles_count
                            if result.saved_to_db:
                                self.stats['saved_to_db'] += 1
                            else:
                                self.stats['db_save_failures'] += 1
                                if result.db_error_message:
                                    errors.append(f"{symbol} DB save failed: {result.db_error_message}")
                        else:
                            self.stats['failed_loads'] += 1
                            if result.error_message:
                                errors.append(f"{symbol}: {result.error_message}")
                        
                        completed += 1
                        
                        # Progress callback
                        if progress_callback:
                            progress_callback(completed, total_symbols, result)
                            
                    except Exception as e:
                        error_msg = f"Unexpected error processing {symbol}: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        completed += 1
        
        # Finalize statistics
        self.stats['end_time'] = datetime.now()
        self.stats['total_duration'] = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        # Calculate database save statistics
        total_db_save_duration = sum(r.db_save_duration for r in results if r.saved_to_db)
        
        # Create report
        report = BatchLoadReport(
            total_symbols=total_symbols,
            successful_loads=self.stats['successful_loads'],
            failed_loads=self.stats['failed_loads'],
            total_candles=self.stats['total_candles'],
            total_duration=self.stats['total_duration'],
            start_time=self.stats['start_time'],
            end_time=self.stats['end_time'],
            results=results,
            errors=errors,
            saved_to_db=self.stats['saved_to_db'],
            db_save_failures=self.stats['db_save_failures'],
            total_db_save_duration=total_db_save_duration
        )
        
        logger.info(f"Batch save completed: {report.successful_loads}/{total_symbols} symbols loaded, "
                   f"{report.saved_to_db}/{report.successful_loads} saved to database")
        
        return report


def create_batch_loader(data_directory: Optional[str] = None, parser_type: Optional[str] = None) -> BatchCSVLoader:
    """
    Convenience function to create a BatchCSVLoader instance.
    
    Args:
        data_directory: Path to directory containing CSV data files
        parser_type: Specific CSV parser type to use
        
    Returns:
        BatchCSVLoader instance
    """
    return BatchCSVLoader(data_directory, parser_type)
