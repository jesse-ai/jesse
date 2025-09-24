#!/usr/bin/env python3
"""
Test symbols through Jesse API
"""

import requests
import json

def test_api_symbols():
    """Test symbols through Jesse API"""
    print("🧪 Тест символов через Jesse API")
    print("=" * 40)
    
    base_url = "http://localhost:9000"
    token = "ef260e9aa3c673af240d17a2660480361a8e081d1ffeca2a5ed0e3219fc18567"
    headers = {"Authorization": token}
    
    try:
        # Test 1: Check if Custom CSV is available
        print("1️⃣ Проверяем доступные exchanges...")
        response = requests.get(f"{base_url}/exchange/supported-symbols", 
                              headers=headers, 
                              params={"exchange": "Custom CSV"})
        
        if response.status_code == 200:
            data = response.json()
            symbols = data.get('data', [])
            print(f"   ✅ Custom CSV доступен")
            print(f"   📊 Символов: {len(symbols)}")
            if symbols:
                print(f"   📋 Первые 10: {symbols[:10]}")
                
                # Check format
                usdt_symbols = [s for s in symbols if s.endswith('-USDT')]
                print(f"   📊 Символов с суффиксом -USDT: {len(usdt_symbols)}")
                
                if len(usdt_symbols) == len(symbols):
                    print("   ✅ Все символы в формате SYMBOL-USDT")
                else:
                    print("   ❌ Не все символы в формате SYMBOL-USDT")
        else:
            print(f"   ❌ Ошибка: {response.status_code} - {response.text}")
            return
        
        print("\n🎉 Тест завершен!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_symbols()
