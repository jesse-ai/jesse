#!/usr/bin/env python3
"""
Test complete CustomCSV driver with all required fields
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_custom_driver_complete():
    """Test complete CustomCSV driver"""
    print("🧪 Тест полного CustomCSV driver")
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
        test_symbols = ['ACH', 'ACH-USDT']
        
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
                    print(f"   📊 Тип первой свечи: {type(candles[0])}")
                    if isinstance(candles[0], dict):
                        print(f"   📊 Ключи: {list(candles[0].keys())}")
                        
                        # Check if all required keys are present
                        required_keys = ['timestamp', 'open', 'close', 'high', 'low', 'volume', 'symbol', 'exchange', 'timeframe']
                        missing_keys = [key for key in required_keys if key not in candles[0]]
                        if missing_keys:
                            print(f"   ❌ Отсутствующие ключи: {missing_keys}")
                        else:
                            print(f"   ✅ Все необходимые ключи присутствуют")
                        
                        # Check values
                        print(f"   📊 timestamp: {candles[0]['timestamp']}")
                        print(f"   📊 symbol: {candles[0]['symbol']}")
                        print(f"   📊 exchange: {candles[0]['exchange']}")
                        print(f"   📊 timeframe: {candles[0]['timeframe']}")
                    else:
                        print(f"   ❌ Ошибка: свеча не является словарем")
                
            except Exception as e:
                print(f"   ❌ Ошибка для {symbol}: {e}")
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_custom_driver_complete()
