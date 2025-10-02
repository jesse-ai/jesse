#!/usr/bin/env python3
"""
Test import through Jesse API
"""

import requests
import json
import time

def test_import_api():
    """Test import through Jesse API"""
    print("🧪 Тест импорта через Jesse API")
    print("=" * 40)
    
    base_url = "http://localhost:9000"
    token = "ef260e9aa3c673af240d17a2660480361a8e081d1ffeca2a5ed0e3219fc18567"
    headers = {"Authorization": token}
    
    try:
        # Test 1: Check if CustomCSV is available
        print("1️⃣ Проверяем доступные exchanges...")
        response = requests.get(f"{base_url}/exchange/supported-symbols", 
                              headers=headers, 
                              params={"exchange": "CustomCSV"})
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ CustomCSV доступен")
            print(f"   📊 Символов: {len(data.get('data', []))}")
            if data.get('data'):
                print(f"   📋 Первые 5: {data['data'][:5]}")
        else:
            print(f"   ❌ Ошибка: {response.status_code} - {response.text}")
            return
        
        # Test 2: Try to import ACH-USDT
        print("\n2️⃣ Пытаемся импортировать ACH-USDT...")
        
        # First, let's check what symbols are available
        symbols_response = requests.get(f"{base_url}/exchange/supported-symbols", 
                                      headers=headers, 
                                      params={"exchange": "CustomCSV"})
        
        if symbols_response.status_code == 200:
            symbols_data = symbols_response.json()
            available_symbols = symbols_data.get('data', [])
            print(f"   📊 Доступные символы: {len(available_symbols)}")
            
            if 'ACH' in available_symbols:
                print("   ✅ ACH найден в списке символов")
                
                # Try to import
                import_data = {
                    "exchange": "CustomCSV",
                    "symbol": "ACH-USDT",  # Use USDT suffix as Jesse expects
                    "start_date": "2023-01-01",
                    "finish_date": "2023-01-02"
                }
                
                print(f"   📤 Отправляем запрос на импорт: {import_data}")
                
                # Note: We need to find the correct import endpoint
                # Let's try the import candles endpoint
                import_response = requests.post(f"{base_url}/import-candles", 
                                              headers=headers, 
                                              json=import_data)
                
                if import_response.status_code == 200:
                    print("   ✅ Импорт успешен!")
                    print(f"   📊 Ответ: {import_response.json()}")
                else:
                    print(f"   ❌ Ошибка импорта: {import_response.status_code} - {import_response.text}")
            else:
                print("   ❌ ACH не найден в списке символов")
        else:
            print(f"   ❌ Ошибка получения символов: {symbols_response.status_code}")
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_import_api()
