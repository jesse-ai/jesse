#!/usr/bin/env python3
"""
Simple test for CSV data provider
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

from jesse.services.csv_data_provider import csv_data_provider

def test_csv_provider():
    """Test CSV data provider functionality"""
    print("🧪 Тестируем CSV Data Provider")
    print("=" * 40)
    
    # Test 1: Get available symbols
    print("1️⃣ Получаем список символов...")
    symbols = csv_data_provider.get_available_symbols()
    print(f"   ✅ Найдено {len(symbols)} символов")
    if symbols:
        print(f"   📋 Первые 5: {symbols[:5]}")
    
    # Test 2: Get symbol info for ACH
    if symbols and 'ACH' in symbols:
        print("\n2️⃣ Получаем информацию о ACH...")
        info = csv_data_provider.get_symbol_info('ACH')
        if info:
            print(f"   ✅ Период: {info['start_date']} - {info['end_date']}")
            print(f"   ✅ Размер файла: {info['file_size']:,} байт")
        else:
            print("   ❌ Не удалось получить информацию")
    
    # Test 3: Load tick data for ACH
    if symbols and 'ACH' in symbols:
        print("\n3️⃣ Загружаем tick данные для ACH...")
        tick_data = csv_data_provider.load_tick_data('ACH')
        if tick_data is not None:
            print(f"   ✅ Загружено {len(tick_data)} записей")
            print(f"   📊 Первые 3 записи:")
            print(tick_data.head(3))
        else:
            print("   ❌ Не удалось загрузить tick данные")
    
    # Test 4: Get candles for ACH
    if symbols and 'ACH' in symbols:
        print("\n4️⃣ Получаем свечи для ACH...")
        candles = csv_data_provider.get_candles('ACH', '1m')
        if candles is not None and len(candles) > 0:
            print(f"   ✅ Получено {len(candles)} свечей")
            print(f"   📊 Первая свеча: {candles[0]}")
        else:
            print("   ❌ Не удалось получить свечи")

if __name__ == "__main__":
    try:
        test_csv_provider()
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
