#!/usr/bin/env python3
"""
Test symbol mapping in CustomCSV driver
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_symbol_mapping():
    """Test symbol mapping"""
    print("🧪 Тест mapping символов в CustomCSV driver")
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
        
        # Test different symbol formats
        test_symbols = ['ACH', 'ACH-USDT', 'BTC-USDT', 'ETH-USDC']
        
        for symbol in test_symbols:
            print(f"\n3️⃣ Тестируем символ: {symbol}")
            
            try:
                # Test get_starting_time
                start_time = driver.get_starting_time(symbol)
                print(f"   ✅ Начальное время: {start_time}")
                
                # Test fetch
                candles = driver.fetch(symbol, start_time, '1m')
                print(f"   ✅ Получено {len(candles)} свечей")
                if candles:
                    print(f"   📊 Первая свеча: {candles[0]}")
                
            except Exception as e:
                print(f"   ❌ Ошибка для {symbol}: {e}")
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_symbol_mapping()
