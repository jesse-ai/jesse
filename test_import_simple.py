#!/usr/bin/env python3
"""
Simple test for CSV import functionality
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

# Test CSV data provider directly
from jesse.services.csv_data_provider import csv_data_provider

def test_import():
    """Test CSV import functionality"""
    print("🧪 Тестируем CSV импорт")
    print("=" * 30)
    
    # Test 1: Load tick data
    print("1️⃣ Загружаем tick данные для IMT...")
    tick_data = csv_data_provider.load_tick_data('IMT')
    if tick_data is not None:
        print(f"   ✅ Загружено {len(tick_data)} записей")
        print(f"   📊 Первые 3 записи:")
        print(tick_data.head(3))
    else:
        print("   ❌ Не удалось загрузить tick данные")
        return
    
    # Test 2: Aggregate to candles
    print("\n2️⃣ Агрегируем в свечи...")
    candles = csv_data_provider.aggregate_to_candles(tick_data, '1m')
    if candles is not None and len(candles) > 0:
        print(f"   ✅ Получено {len(candles)} свечей")
        print(f"   📊 Первая свеча: {candles[0]}")
        print(f"   📊 Последняя свеча: {candles[-1]}")
    else:
        print("   ❌ Не удалось агрегировать в свечи")
        return
    
    # Test 3: Try to save to database (this might fail without proper DB setup)
    print("\n3️⃣ Пытаемся сохранить в базу данных...")
    try:
        success = csv_data_provider.save_candles_to_database('IMT', '1m', 'custom')
        if success:
            print("   ✅ Успешно сохранено в базу данных")
        else:
            print("   ❌ Не удалось сохранить в базу данных")
    except Exception as e:
        print(f"   ❌ Ошибка при сохранении: {e}")

if __name__ == "__main__":
    try:
        test_import()
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
