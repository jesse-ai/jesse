#!/usr/bin/env python3
"""
Simple test for CSV data provider without full Jesse import
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

class SimpleCSVDataProvider:
    """
    Simple CSV data provider for testing
    """
    
    def __init__(self, data_directory: str = "/Users/alxy/Downloads/Fond/KucoinData"):
        self.data_directory = data_directory
        self.cache = {}
        
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols from data directory."""
        if not os.path.exists(self.data_directory):
            print(f"❌ Директория {self.data_directory} не существует")
            return []
            
        symbols = []
        for item in os.listdir(self.data_directory):
            item_path = os.path.join(self.data_directory, item)
            if os.path.isdir(item_path):
                # Check if price.csv exists in the directory
                price_file = os.path.join(item_path, "price.csv")
                if os.path.exists(price_file):
                    symbols.append(item)
                    
        return sorted(symbols)
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get information about a specific symbol."""
        symbol_dir = os.path.join(self.data_directory, symbol)
        price_file = os.path.join(symbol_dir, "price.csv")
        
        if not os.path.exists(price_file):
            return None
            
        try:
            # Get file size
            file_size = os.path.getsize(price_file)
            
            # Read first and last lines to get time range
            with open(price_file, 'r') as f:
                first_line = f.readline().strip()  # Skip header
                first_line = f.readline().strip()  # Get first data line
                f.seek(0, 2)  # Go to end of file
                f.seek(f.tell() - 1000, 0)  # Go back 1000 bytes
                lines = f.readlines()
                last_line = lines[-1].strip() if lines else first_line
            
            # Parse timestamps
            first_parts = first_line.split(',')
            last_parts = last_line.split(',')
            
            if len(first_parts) >= 1 and len(last_parts) >= 1:
                start_timestamp = int(first_parts[0])
                end_timestamp = int(last_parts[0])
                
                # Convert to readable dates
                start_date = pd.to_datetime(start_timestamp, unit='ms').strftime('%Y-%m-%d %H:%M:%S')
                end_date = pd.to_datetime(end_timestamp, unit='ms').strftime('%Y-%m-%d %H:%M:%S')
                
                return {
                    'symbol': symbol,
                    'start_time': start_timestamp,
                    'end_time': end_timestamp,
                    'start_date': start_date,
                    'end_date': end_date,
                    'file_path': price_file,
                    'file_size': file_size
                }
        except Exception as e:
            print(f"❌ Ошибка при чтении файла {price_file}: {e}")
            return None
            
        return None

def test_csv_provider():
    """Test CSV data provider functionality"""
    print("🧪 Тестируем Simple CSV Data Provider")
    print("=" * 40)
    
    # Create provider
    provider = SimpleCSVDataProvider()
    
    # Test 1: Get available symbols
    print("1️⃣ Получаем список символов...")
    symbols = provider.get_available_symbols()
    print(f"   ✅ Найдено {len(symbols)} символов")
    if symbols:
        print(f"   📋 Первые 5: {symbols[:5]}")
    
    # Test 2: Get symbol info for ACH
    if symbols and 'ACH' in symbols:
        print("\n2️⃣ Получаем информацию о ACH...")
        info = provider.get_symbol_info('ACH')
        if info:
            print(f"   ✅ Период: {info['start_date']} - {info['end_date']}")
            print(f"   ✅ Размер файла: {info['file_size']:,} байт")
        else:
            print("   ❌ Не удалось получить информацию")
    else:
        print("   ❌ Символ ACH не найден в списке")

if __name__ == "__main__":
    try:
        test_csv_provider()
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
