#!/usr/bin/env python3
"""
Test symbols format in CustomCSV driver
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_symbols_format():
    """Test symbols format"""
    print("🧪 Тест формата символов в CustomCSV driver")
    print("=" * 50)
    
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
        print(f"   ✅ Получено {len(symbols)} символов")
        print(f"   📋 Первые 10: {symbols[:10]}")
        
        # Check format
        print("\n4️⃣ Проверяем формат символов...")
        usdt_symbols = [s for s in symbols if s.endswith('-USDT')]
        print(f"   📊 Символов с суффиксом -USDT: {len(usdt_symbols)}")
        
        if len(usdt_symbols) == len(symbols):
            print("   ✅ Все символы в формате SYMBOL-USDT")
        else:
            print("   ❌ Не все символы в формате SYMBOL-USDT")
        
        # Test a few symbols
        print("\n5️⃣ Тестируем несколько символов...")
        test_symbols = symbols[:3]  # Test first 3 symbols
        
        for symbol in test_symbols:
            try:
                # Test get_starting_time
                start_time = driver.get_starting_time(symbol)
                print(f"   ✅ {symbol}: Начальное время: {start_time}")
                
                # Test fetch
                candles = driver.fetch(symbol, start_time, '1m')
                print(f"   ✅ {symbol}: Получено {len(candles)} свечей")
                
            except Exception as e:
                print(f"   ❌ {symbol}: Ошибка: {e}")
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_symbols_format()
