#!/usr/bin/env python3
"""
Detailed test for CSV import functionality
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_import_detailed():
    """Test CSV import functionality with detailed error reporting"""
    print("🧪 Детальный тест CSV импорта")
    print("=" * 40)
    
    try:
        # Set Jesse project directory
        import os
        os.chdir('/Users/alxy/Desktop/1PROJ/JesseLocal/project-template')
        print(f"   📊 Рабочая директория: {os.getcwd()}")
        
        from jesse.services.csv_data_provider import csv_data_provider
        print("1️⃣ Импорт CSV data provider... ✅")
        
        # Test 1: Load tick data
        print("\n2️⃣ Загружаем tick данные для IMT...")
        tick_data = csv_data_provider.load_tick_data('IMT')
        if tick_data is not None:
            print(f"   ✅ Загружено {len(tick_data)} записей")
        else:
            print("   ❌ Не удалось загрузить tick данные")
            return
        
        # Test 2: Aggregate to candles
        print("\n3️⃣ Агрегируем в свечи...")
        candles = csv_data_provider.aggregate_to_candles(tick_data, '1m')
        if candles is not None and len(candles) > 0:
            print(f"   ✅ Получено {len(candles)} свечей")
        else:
            print("   ❌ Не удалось агрегировать в свечи")
            return
        
        # Test 3: Try to save to database with detailed error reporting
        print("\n4️⃣ Пытаемся сохранить в базу данных...")
        try:
            from jesse.services.db import database
            import jesse.helpers as jh
            
            print("   📊 Проверяем условия подключения...")
            print(f"   📊 is_jesse_project(): {jh.is_jesse_project()}")
            print(f"   📊 is_unit_testing(): {jh.is_unit_testing()}")
            
            print("   📊 Открываем подключение к базе данных...")
            database.open_connection()
            print(f"   📊 database.db: {database.db}")
            print("   ✅ Подключение открыто")
            
            print("   📊 Запускаем миграции базы данных...")
            from jesse.services.migrator import run as run_migrations
            run_migrations()
            print("   ✅ Миграции выполнены")
            
            # Use the Jesse approach for database operations
            print("   📊 Используем Jesse подход для работы с базой данных...")
            from jesse.models.Candle import fetch_candles_from_db, store_candles_into_db
            
            print("   📊 Подготавливаем данные для вставки...")
            # Convert candles to Jesse format
            jesse_candles = []
            for i, candle in enumerate(candles[:100]):  # Только первые 100 свечей для теста
                jesse_candles.append([
                    int(candle[0]),    # timestamp
                    float(candle[1]),  # open
                    float(candle[2]),  # close
                    float(candle[3]),  # high
                    float(candle[4]),  # low
                    float(candle[5])   # volume
                ])
            
            print(f"   📊 Подготовлено {len(jesse_candles)} свечей для вставки")
            
            print("   📊 Вставляем данные в базу используя Jesse store_candles_into_db...")
            import numpy as np
            store_candles_into_db('custom', 'IMT', '1m', np.array(jesse_candles))
            print("   ✅ Данные успешно вставлены!")
            
            # Verify insertion
            print("   📊 Проверяем вставленные данные...")
            stored_candles = fetch_candles_from_db('custom', 'IMT', '1m', 0, 9999999999999)
            print(f"   📊 Проверка: в базе {len(stored_candles)} записей для IMT")
            
            database.close_connection()
            print("   ✅ Подключение закрыто")
            
        except Exception as e:
            print(f"   ❌ Ошибка при работе с базой данных: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"\n❌ Общая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_import_detailed()
