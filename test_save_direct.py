#!/usr/bin/env python3
"""
Direct test for save_candles_to_database function
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_save_direct():
    """Test save_candles_to_database function directly"""
    print("🧪 Прямой тест save_candles_to_database")
    print("=" * 50)
    
    try:
        # Set Jesse project directory
        os.chdir('/Users/alxy/Desktop/1PROJ/JesseLocal/project-template')
        print(f"   📊 Рабочая директория: {os.getcwd()}")
        
        from jesse.services.csv_data_provider import csv_data_provider
        print("1️⃣ Импорт CSV data provider... ✅")
        
        # Test save_candles_to_database directly
        print("\n2️⃣ Тестируем save_candles_to_database для ACH...")
        
        # First check if we have candles
        candles = csv_data_provider.get_candles('ACH', '1m')
        if candles is not None:
            print(f"   📊 Найдено {len(candles)} свечей для ACH")
        else:
            print("   ❌ Нет свечей для ACH")
            return
        
        result = csv_data_provider.save_candles_to_database('ACH', '1m')
        
        if result:
            print("   ✅ Данные успешно сохранены!")
        else:
            print("   ❌ Ошибка при сохранении данных")
            
    except Exception as e:
        print(f"\n❌ Общая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_save_direct()
