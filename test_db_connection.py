#!/usr/bin/env python3
"""
Test database connection
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

def test_db_connection():
    """Test database connection"""
    print("🧪 Тестируем подключение к базе данных")
    print("=" * 40)
    
    try:
        from jesse.services.db import database
        print("1️⃣ Импорт database модуля... ✅")
        
        # Try to open connection
        database.open_connection()
        print("2️⃣ Открытие подключения... ✅")
        
        # Check if we can query
        from jesse.models.Candle import Candle
        print("3️⃣ Импорт Candle модели... ✅")
        
        # Try to count candles
        count = Candle.select().count()
        print(f"4️⃣ Количество свечей в базе: {count}")
        
        # Close connection
        database.close_connection()
        print("5️⃣ Закрытие подключения... ✅")
        
        print("\n✅ База данных работает правильно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка с базой данных: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_db_connection()
