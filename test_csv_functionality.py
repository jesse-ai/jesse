#!/usr/bin/env python3
"""
Simple test script for CSV functionality in Jesse.
This script tests the CSV data provider and parser functionality.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

from jesse.services.csv_data_provider import csv_data_provider
from jesse.services.csv_parser import CSVParser
import jesse.helpers as jh


def test_csv_data_provider():
    """Test CSV data provider functionality."""
    print("Testing CSV Data Provider...")
    
    # Test getting available symbols
    symbols = csv_data_provider.get_available_symbols()
    print(f"Available symbols: {symbols[:10]}...")  # Show first 10
    
    if not symbols:
        print("No symbols found. Make sure CSV data directory is correct.")
        return False
    
    # Test getting symbol info
    test_symbol = symbols[0]
    info = csv_data_provider.get_symbol_info(test_symbol)
    if info:
        print(f"Symbol info for {test_symbol}:")
        print(f"  Start time: {info['start_time']} ({info['start_date']})")
        print(f"  End time: {info['end_time']} ({info['end_date']})")
        print(f"  File size: {info['file_size']} bytes")
    else:
        print(f"Could not get info for {test_symbol}")
        return False
    
    # Test loading tick data
    print(f"\nLoading tick data for {test_symbol}...")
    tick_data = csv_data_provider.load_tick_data(test_symbol, limit=1000)
    if tick_data is not None:
        print(f"Loaded {len(tick_data)} ticks")
        print(f"First few ticks:")
        print(tick_data.head())
    else:
        print("Failed to load tick data")
        return False
    
    # Test aggregating to candles
    print(f"\nAggregating to 1m candles...")
    candles = csv_data_provider.aggregate_to_candles(tick_data, "1m")
    if len(candles) > 0:
        print(f"Generated {len(candles)} 1m candles")
        print(f"First candle: {candles[0]}")
    else:
        print("Failed to generate candles")
        return False
    
    return True


def test_csv_parser():
    """Test CSV parser functionality."""
    print("\nTesting CSV Parser...")
    
    # Find a CSV file to test with
    data_dir = "/Users/alxy/Downloads/Fond/KucoinData"
    test_file = None
    
    for symbol in os.listdir(data_dir):
        symbol_path = os.path.join(data_dir, symbol)
        if os.path.isdir(symbol_path):
            price_file = os.path.join(symbol_path, "price.csv")
            if os.path.exists(price_file):
                test_file = price_file
                break
    
    if not test_file:
        print("No CSV file found for testing")
        return False
    
    print(f"Testing with file: {test_file}")
    
    # Test CSV parser
    parser = CSVParser(test_file, "custom", "TEST", "1m")
    
    # Test validation
    if not parser.validate_file():
        print("File validation failed")
        return False
    
    # Test column detection
    columns = parser.detect_columns()
    print(f"Detected columns: {columns}")
    
    # Test parsing
    if not parser.parse_csv():
        print("CSV parsing failed")
        return False
    
    # Get candles
    candles = parser.get_candles()
    if candles is not None and len(candles) > 0:
        print(f"Parsed {len(candles)} candles")
        print(f"First candle: {candles[0]}")
    else:
        print("No candles parsed")
        return False
    
    # Get candles info
    info = parser.get_candles_info()
    print(f"Candles info: {info}")
    
    return True


def main():
    """Main test function."""
    print("=== Jesse CSV Functionality Test ===\n")
    
    success = True
    
    # Test CSV data provider
    if not test_csv_data_provider():
        success = False
    
    # Test CSV parser
    if not test_csv_parser():
        success = False
    
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
    
    return success


if __name__ == "__main__":
    main()
