#!/usr/bin/env python3
"""
Test updated CSV data provider with symbol mapping
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_csv_provider_updated():
    """Test updated CSV data provider"""
    print("🧪 Тест обновленного CSV data provider")
    print("=" * 50)
    
    try:
        # Set Jesse project directory
        os.chdir('/Users/alxy/Desktop/1PROJ/JesseLocal/project-template')
        print(f"   📊 Рабочая директория: {os.getcwd()}")
        
        from jesse.services.csv_data_provider import CSVDataProvider
        print("1️⃣ Импорт CSVDataProvider... ✅")
        
        # Create provider instance
        provider = CSVDataProvider()
        print("2️⃣ Создание provider instance... ✅")
        
        # Test different symbol formats
        test_symbols = ['ACH', 'ACH-USDT', 'BTC-USDT', 'ETH-USDC']
        
        for symbol in test_symbols:
            print(f"\n3️⃣ Тестируем символ: {symbol}")
            
            try:
                # Test get_symbol_info
                symbol_info = provider.get_symbol_info(symbol)
                if symbol_info:
                    print(f"   ✅ Symbol info: {symbol_info['symbol']} ({symbol_info['start_date']} - {symbol_info['end_date']})")
                else:
                    print(f"   ❌ Symbol info not found")
                
                # Test get_candles
                candles = provider.get_candles(symbol, '1m')
                if candles is not None and len(candles) > 0:
                    print(f"   ✅ Получено {len(candles)} свечей")
                    print(f"   📊 Первая свеча: {candles[0]}")
                else:
                    print(f"   ❌ Свечи не найдены")
                
            except Exception as e:
                print(f"   ❌ Ошибка для {symbol}: {e}")
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_csv_provider_updated()
