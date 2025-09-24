#!/usr/bin/env python3
"""
Quick Test Script for CSV Data Loading
Быстрый тест загрузки CSV данных
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

from jesse.research.external_data.csv_ticks_to_db import CSVDataLoader, BASE_URL, AUTHORIZATION

def quick_test():
    """Быстрый тест функциональности"""
    print("🧪 Быстрый тест CSV функциональности")
    print("=" * 40)
    
    # Создание загрузчика
    loader = CSVDataLoader(BASE_URL, AUTHORIZATION)
    
    # 1. Тест получения символов
    print("1️⃣ Получаем список символов...")
    symbols = loader.get_available_symbols()
    print(f"   ✅ Найдено {len(symbols)} символов")
    if symbols:
        print(f"   📋 Первые 5: {symbols[:5]}")
    
    # 2. Тест информации о символе
    if symbols:
        test_symbol = symbols[0]
        print(f"\n2️⃣ Получаем информацию о {test_symbol}...")
        try:
            info = loader.get_symbol_info(test_symbol)
            if info:
                print(f"   ✅ Период: {info['start_date']} - {info['end_date']}")
                print(f"   ✅ Размер файла: {info['file_size']:,} байт")
            else:
                print("   ❌ Не удалось получить информацию")
        except Exception as e:
            print(f"   ❌ Ошибка получения информации: {e}")
    
    # 3. Тест предварительного просмотра
    if symbols:
        print(f"\n3️⃣ Предварительный просмотр {test_symbol}...")
        try:
            preview = loader.preview_data(test_symbol, limit=3)
            if preview:
                print("   ✅ Данные:")
                for i, row in enumerate(preview.get('preview', [])[:3]):
                    print(f"      {i+1}. {row}")
            else:
                print("   ❌ Не удалось получить предварительный просмотр")
        except Exception as e:
            print(f"   ❌ Ошибка предварительного просмотра: {e}")
    
    # 4. Тест импорта (только один символ)
    if symbols:
        print(f"\n4️⃣ Тестируем импорт {test_symbol}...")
        try:
            success = loader.import_symbol(test_symbol, "1m", "custom")
            if success:
                print("   ✅ Импорт успешен")
                
                # Проверяем загруженные свечи
                candles_data = loader.get_candles(test_symbol, "1m")
                if candles_data:
                    count = candles_data.get('count', 0)
                    print(f"   📊 Загружено {count:,} свечей")
            else:
                print("   ❌ Ошибка импорта")
        except Exception as e:
            print(f"   ❌ Ошибка импорта: {e}")
    
    # 5. Тест очистки кэша
    print(f"\n5️⃣ Очищаем кэш...")
    loader.clear_cache()
    
    print("\n🎉 Тест завершен!")

def test_specific_symbols():
    """Тест конкретных символов"""
    print("\n🎯 Тест конкретных символов")
    print("=" * 30)
    
    loader = CSVDataLoader(BASE_URL, AUTHORIZATION)
    
    # Список символов для тестирования
    test_symbols = ["ACH", "CAS", "DOGS"]
    
    for symbol in test_symbols:
        print(f"\n📊 Тестируем {symbol}...")
        
        # Проверяем доступность
        available_symbols = loader.get_available_symbols()
        if symbol not in available_symbols:
            print(f"   ❌ Символ {symbol} не найден")
            continue
        
        # Получаем информацию
        try:
            info = loader.get_symbol_info(symbol)
            if info:
                print(f"   ✅ Период: {info['start_date']} - {info['end_date']}")
        except Exception as e:
            print(f"   ❌ Ошибка получения информации: {e}")
        
        # Импортируем
        try:
            success = loader.import_symbol(symbol, "1m", "custom")
            if success:
                print(f"   ✅ {symbol} импортирован успешно")
            else:
                print(f"   ❌ Ошибка импорта {symbol}")
        except Exception as e:
            print(f"   ❌ Ошибка импорта {symbol}: {e}")

if __name__ == "__main__":
    try:
        # Основной тест
        quick_test()
        
        # Тест конкретных символов
        test_specific_symbols()
        
    except KeyboardInterrupt:
        print("\n⏹️  Тест прерван пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
