#!/usr/bin/env python3
"""
Test available exchanges including Custom CSV
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_exchanges():
    """Test available exchanges"""
    print("🧪 Тест доступных exchanges")
    print("=" * 40)
    
    try:
        # Set Jesse project directory
        os.chdir('/Users/alxy/Desktop/1PROJ/JesseLocal/project-template')
        print(f"   📊 Рабочая директория: {os.getcwd()}")
        
        from jesse.modes.import_candles_mode.drivers import driver_names
        from jesse.enums import exchanges
        print("1️⃣ Импорт driver_names и exchanges... ✅")
        
        print(f"\n2️⃣ Доступные exchanges ({len(driver_names)}):")
        for i, exchange in enumerate(driver_names, 1):
            print(f"   {i:2d}. {exchange}")
        
        # Check if Custom CSV is in the list
        if exchanges.CUSTOM_CSV in driver_names:
            print(f"\n✅ Custom CSV найден в списке: {exchanges.CUSTOM_CSV}")
        else:
            print(f"\n❌ Custom CSV НЕ найден в списке")
            print(f"   Ищем: {exchanges.CUSTOM_CSV}")
            print(f"   В списке: {driver_names}")
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_exchanges()
