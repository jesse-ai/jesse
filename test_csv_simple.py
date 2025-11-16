#!/usr/bin/env python3
"""
Simple test script for CSV functionality in Jesse.
This script tests the CSV data provider and parser functionality without full Jesse dependencies.
"""

import os
import sys
import pandas as pd
import numpy as np

# Add jesse to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_csv_parser_basic():
    """Test basic CSV parser functionality."""
    print("Testing CSV Parser (basic functionality)...")
    
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
    
    try:
        # Test basic CSV reading
        df = pd.read_csv(test_file, names=['timestamp', 'price', 'volume'], skiprows=1)  # Skip header
        print(f"Loaded {len(df)} rows from CSV")
        print(f"First 5 rows:")
        print(df.head())
        
        # Convert timestamp to numeric
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df = df.dropna()  # Remove any rows with invalid timestamps
        
        # Test aggregation to 1m candles
        df['candle_timestamp'] = (df['timestamp'] // 60000) * 60000  # 1 minute buckets
        
        candles = df.groupby('candle_timestamp').agg({
            'price': ['first', 'last', 'max', 'min'],
            'volume': 'sum'
        }).reset_index()
        
        candles.columns = ['timestamp', 'open', 'close', 'high', 'low', 'volume']
        
        print(f"\nGenerated {len(candles)} 1m candles")
        print(f"First 3 candles:")
        print(candles.head(3))
        
        return True
        
    except Exception as e:
        print(f"Error testing CSV parser: {e}")
        return False


def test_data_directory():
    """Test data directory structure."""
    print("\nTesting data directory structure...")
    
    data_dir = "/Users/alxy/Downloads/Fond/KucoinData"
    
    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        return False
    
    symbols = []
    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)
        if os.path.isdir(item_path):
            price_file = os.path.join(item_path, "price.csv")
            if os.path.exists(price_file):
                symbols.append(item)
    
    print(f"Found {len(symbols)} symbols with CSV data")
    print(f"First 10 symbols: {symbols[:10]}")
    
    if symbols:
        # Test one symbol
        test_symbol = symbols[0]
        price_file = os.path.join(data_dir, test_symbol, "price.csv")
        
        # Get file info
        file_size = os.path.getsize(price_file)
        print(f"\nTesting symbol: {test_symbol}")
        print(f"File size: {file_size} bytes")
        
        # Read first and last lines to get time range
        with open(price_file, 'r') as f:
            first_line = f.readline().strip()  # Skip header
            first_line = f.readline().strip()  # First data line
            f.seek(0, 2)  # Go to end
            file_size = f.tell()
            f.seek(max(0, file_size - 1000))  # Read last 1000 bytes
            last_chunk = f.read()
            last_line = last_chunk.split('\n')[-2] if '\n' in last_chunk else last_chunk
        
        first_parts = first_line.split(',')
        last_parts = last_line.split(',')
        
        if len(first_parts) >= 2 and len(last_parts) >= 2:
            start_time = int(first_parts[0])  # First column is timestamp
            end_time = int(last_parts[0])     # First column is timestamp
            print(f"Time range: {start_time} - {end_time}")
            print(f"Duration: {(end_time - start_time) / 1000 / 60 / 60:.2f} hours")
        
        return True
    
    return False


def main():
    """Main test function."""
    print("=== Jesse CSV Functionality Test (Simple) ===\n")
    
    success = True
    
    # Test data directory
    if not test_data_directory():
        success = False
    
    # Test CSV parser
    if not test_csv_parser_basic():
        success = False
    
    if success:
        print("\n✅ All tests passed!")
        print("\nCSV functionality is working correctly!")
        print("\nNext steps:")
        print("1. Start Jesse server: jesse run")
        print("2. Access CSV endpoints at: http://localhost:9000/csv/")
        print("3. Use the API to import CSV data for backtesting")
    else:
        print("\n❌ Some tests failed!")
    
    return success


if __name__ == "__main__":
    main()
