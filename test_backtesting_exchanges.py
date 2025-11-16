#!/usr/bin/env python3
"""
Test backtesting exchanges including Custom CSV
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_backtesting_exchanges():
    """Test backtesting exchanges"""
    print("🧪 Тест backtesting exchanges")
    print("=" * 40)
    
    try:
        # Set Jesse project directory
        os.chdir('/Users/alxy/Desktop/1PROJ/JesseLocal/project-template')
        print(f"   📊 Рабочая директория: {os.getcwd()}")
        
        from jesse.info import backtesting_exchanges, live_trading_exchanges
        from jesse.enums import exchanges
        print("1️⃣ Импорт backtesting_exchanges и live_trading_exchanges... ✅")
        
        print(f"\n2️⃣ Backtesting exchanges ({len(backtesting_exchanges)}):")
        for i, exchange in enumerate(backtesting_exchanges, 1):
            print(f"   {i:2d}. {exchange}")
        
        print(f"\n3️⃣ Live trading exchanges ({len(live_trading_exchanges)}):")
        for i, exchange in enumerate(live_trading_exchanges, 1):
            print(f"   {i:2d}. {exchange}")
        
        # Check if Custom CSV is in backtesting exchanges
        if exchanges.CUSTOM_CSV in backtesting_exchanges:
            print(f"\n✅ Custom CSV найден в backtesting exchanges: {exchanges.CUSTOM_CSV}")
        else:
            print(f"\n❌ Custom CSV НЕ найден в backtesting exchanges")
            print(f"   Ищем: {exchanges.CUSTOM_CSV}")
            print(f"   В списке: {backtesting_exchanges}")
        
        # Check if Custom CSV is in live trading exchanges
        if exchanges.CUSTOM_CSV in live_trading_exchanges:
            print(f"\n✅ Custom CSV найден в live trading exchanges: {exchanges.CUSTOM_CSV}")
        else:
            print(f"\n❌ Custom CSV НЕ найден в live trading exchanges (это нормально)")
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_backtesting_exchanges()
