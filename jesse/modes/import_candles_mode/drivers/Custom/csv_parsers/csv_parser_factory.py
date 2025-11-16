"""
CSV Parser Factory for CustomCSV driver.

This factory automatically detects CSV format and creates appropriate parser.
"""

import os
from typing import Optional, Dict, Any
from .base_csv_parser import BaseCSVParser
from .kucoin_csv_parser import KucoinCSVParser
import jesse.helpers as jh
from jesse.services import logger


class CSVParserFactory:
    """
    Factory class for creating CSV parsers based on detected format.
    """
    
    # Registry of available parsers
    _parsers = {
        'kucoin': KucoinCSVParser,
        # Add more parsers here as needed
        # 'binance': BinanceCSVParser,
        # 'coinbase': CoinbaseCSVParser,
    }
    
    @classmethod
    def create_parser(cls, data_directory: str, parser_type: Optional[str] = None) -> BaseCSVParser:
        """
        Create CSV parser for the given data directory.
        
        Args:
            data_directory: Path to data directory
            parser_type: Specific parser type to use (optional)
            
        Returns:
            Appropriate CSV parser instance
        """
        if parser_type:
            if parser_type not in cls._parsers:
                raise ValueError(f"Unknown parser type: {parser_type}. Available: {list(cls._parsers.keys())}")
            return cls._parsers[parser_type](data_directory)
        
        # Auto-detect format
        detected_type = cls.detect_format(data_directory)
        if detected_type:
            logger.info(f"Auto-detected CSV format: {detected_type}")
            return cls._parsers[detected_type](data_directory)
        
        # Default to KucoinCSVParser for backward compatibility
        logger.info("Using default KucoinCSVParser")
        return KucoinCSVParser(data_directory)
    
    @classmethod
    def detect_format(cls, data_directory: str) -> Optional[str]:
        """
        Detect CSV format by examining files in the directory.
        
        Args:
            data_directory: Path to data directory
            
        Returns:
            Detected format type or None if unknown
        """
        if not os.path.exists(data_directory):
            return None
        
        # Look for sample files to detect format
        sample_files = []
        for item in os.listdir(data_directory):
            item_path = os.path.join(data_directory, item)
            if os.path.isdir(item_path):
                # Check for common CSV file names
                for csv_file in ['price.csv', 'data.csv', 'trades.csv', 'klines.csv']:
                    file_path = os.path.join(item_path, csv_file)
                    if os.path.exists(file_path):
                        sample_files.append(file_path)
                        break
                
                # Limit to first few files for performance
                if len(sample_files) >= 3:
                    break
        
        if not sample_files:
            return None
        
        # Analyze sample files to detect format
        for file_path in sample_files:
            format_type = cls._analyze_file_format(file_path)
            if format_type:
                return format_type
        
        return None
    
    @classmethod
    def _analyze_file_format(cls, file_path: str) -> Optional[str]:
        """
        Analyze a single file to determine its format.
        
        Args:
            file_path: Path to CSV file
            
        Returns:
            Detected format type or None
        """
        try:
            with open(file_path, 'r') as f:
                # Read first few lines
                lines = []
                for i, line in enumerate(f):
                    if i >= 5:  # Read max 5 lines
                        break
                    lines.append(line.strip())
            
            if not lines:
                return None
            
            # Check for Kucoin format: t,p,v
            if lines[0] == 't,p,v':
                # Validate data format
                for line in lines[1:]:
                    if not line:
                        continue
                    parts = line.split(',')
                    if len(parts) == 3:
                        try:
                            # Check if first part is timestamp, others are numeric
                            int(parts[0])
                            float(parts[1])
                            float(parts[2])
                            return 'kucoin'
                        except ValueError:
                            break
                    else:
                        break
            
            # Add more format detection logic here
            # elif lines[0] == 'timestamp,open,high,low,close,volume':
            #     return 'binance'
            # elif lines[0] == 'time,price,size':
            #     return 'coinbase'
            
        except Exception as e:
            logger.error(f"Error analyzing file format for {file_path}: {e}")
        
        return None
    
    @classmethod
    def register_parser(cls, name: str, parser_class: type):
        """
        Register a new parser type.
        
        Args:
            name: Parser name
            parser_class: Parser class that inherits from BaseCSVParser
        """
        if not issubclass(parser_class, BaseCSVParser):
            raise ValueError("Parser class must inherit from BaseCSVParser")
        
        cls._parsers[name] = parser_class
        logger.info(f"Registered parser: {name}")
    
    @classmethod
    def get_available_parsers(cls) -> Dict[str, str]:
        """
        Get list of available parsers.
        
        Returns:
            Dictionary mapping parser names to descriptions
        """
        return {
            name: parser_class.__doc__.split('\n')[0] if parser_class.__doc__ else "No description"
            for name, parser_class in cls._parsers.items()
        }
    
    @classmethod
    def get_parser_info(cls, parser_type: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific parser.
        
        Args:
            parser_type: Parser type name
            
        Returns:
            Parser information dictionary or None if not found
        """
        if parser_type not in cls._parsers:
            return None
        
        # Create temporary instance to get info
        try:
            temp_parser = cls._parsers[parser_type]("/tmp")
            return temp_parser.get_parser_info()
        except:
            return {
                'name': parser_type,
                'class': cls._parsers[parser_type].__name__,
                'description': cls._parsers[parser_type].__doc__.split('\n')[0] if cls._parsers[parser_type].__doc__ else "No description"
            }

