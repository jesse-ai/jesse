#!/usr/bin/env python3
"""
Test CustomCSV driver
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_custom_driver():
    """Test CustomCSV driver"""
    print("🧪 Тест CustomCSV driver")
    print("=" * 40)
    
    try:
        # Set Jesse project directory
        os.chdir('/Users/alxy/Desktop/1PROJ/JesseLocal/project-template')
        print(f"   📊 Рабочая директория: {os.getcwd()}")
        
        from jesse.modes.import_candles_mode.drivers.Custom.CustomCSV import CustomCSV
        print("1️⃣ Импорт CustomCSV driver... ✅")
        
        # Create driver instance
        driver = CustomCSV()
        print("2️⃣ Создание driver instance... ✅")
        
        # Test get_available_symbols
        print("\n3️⃣ Тестируем get_available_symbols...")
        symbols = driver.get_available_symbols()
        print(f"   ✅ Найдено {len(symbols)} символов")
        print(f"   📋 Первые 5: {symbols[:5]}")
        
        # Test get_starting_time
        if symbols:
            symbol = symbols[0]
            print(f"\n4️⃣ Тестируем get_starting_time для {symbol}...")
            start_time = driver.get_starting_time(symbol)
            print(f"   ✅ Начальное время: {start_time}")
        
        # Test fetch
        if symbols:
            symbol = symbols[0]
            print(f"\n5️⃣ Тестируем fetch для {symbol}...")
            candles = driver.fetch(symbol, start_time, '1m')
            print(f"   ✅ Получено {len(candles)} свечей")
            if candles:
                print(f"   📊 Первая свеча: {candles[0]}")
        
        print("\n🎉 Все тесты прошли успешно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_custom_driver()
